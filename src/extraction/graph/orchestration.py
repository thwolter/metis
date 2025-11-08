from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from core.config import get_settings

from ..models import ExtractionJob, ExtractionJobStatus
from ..persistence import create_extraction_job, update_job_status
from ..registry import get_attribute_specs
from ..schemas import (
    AttributeResult,
    AttributeSpec,
    ExtractionRequest,
    ExtractionResult,
    RetrievalConfig,
    StatusEvent,
)
from ..utils import resolve_execution_config
from . import phases
from .context import (
    ExtractionCancelledError,
    ExtractionContext,
    build_extraction_context,
)
from .progress import AttributeState, ProgressTracker
from .status import BrokerCallback


def _get_model_name(job: ExtractionJob | None, request: ExtractionRequest, settings) -> str:
    return job.model if job and job.model else request.model or settings.extraction.default_model


def _get_model_version(job: ExtractionJob | None, settings) -> str:
    return job.model_version if job and job.model_version else settings.extraction.model_version


async def _prepare_job(
    session: AsyncSession,
    request: ExtractionRequest,
    job: ExtractionJob | None,
    retrieval_config: RetrievalConfig,
    settings,
) -> ExtractionJob:
    """
    Prepares an extraction job by creating or updating it based on the provided
    request, job, and configuration. The method establishes necessary configuration
    parameters, validates required fields, and ensures the job is in a RUNNING status.

    Parameters:
    - session (AsyncSession): Asynchronous database session used for job creation or
      updates.
    - request (ExtractionRequest): The extraction request containing document details
      and options.
    - job (ExtractionJob | None): Existing extraction job to be updated, or None if a
      new job needs to be created.
    - retrieval_config (RetrievalConfig): Configuration data to be utilized by the job's
      retriever.
    - settings: Configuration settings potentially used to extract model name and version.

    Raises:
    - ValueError: If 'digest', 'collection_name', or 'tenant_id' are not provided for the
      extraction process.

    Returns:
    ExtractionJob: The prepared or updated extraction job in a RUNNING state.
    """
    model_name = _get_model_name(job, request, settings)
    model_version = _get_model_version(job, settings)
    digest = job.document_digest if job else request.digest
    collection_name = job.collection_name if job else request.collection_name
    tenant_id = job.tenant_id if job else request.tenant_id

    if digest is None or collection_name is None:
        raise ValueError('digest and collection_name must be provided for extraction')
    if tenant_id is None:
        raise ValueError('tenant_id must be provided for extraction jobs')

    retriever_snapshot = retrieval_config.model_dump(mode='json')
    if job is None:
        job = await create_extraction_job(
            session,
            tenant_id=tenant_id,
            doc_id=request.doc_id,
            doc_type=request.doc_type,
            model=model_name,
            model_version=model_version,
            retriever_config=retriever_snapshot,
            options={'dry_run': request.dry_run},
            document_digest=digest,
            collection_name=collection_name,
        )
    else:
        if job.model != model_name:
            job.model = model_name
        if job.model_version != model_version:
            job.model_version = model_version
        job.retriever_config = retriever_snapshot
        job.options = {'dry_run': request.dry_run}
        session.add(job)

    return await update_job_status(session, job, status=ExtractionJobStatus.RUNNING)


async def _process_attribute(context: ExtractionContext, spec: AttributeSpec) -> AttributeResult:
    attr_state = context.attribute_states[spec.name]
    attr_state.state = 'mapping'
    await context.ensure_active()
    await context.emitter.emit(
        StatusEvent.ATTRIBUTE_STARTED,
        attribute_payload={'name': spec.name, 'phase': 'retrieve'},
        include_snapshot=True,
    )

    map_chunks = await phases.retrieve_attribute_chunks(context, spec, attr_state)
    candidates = await phases.map_attribute_chunks(context, spec, map_chunks, attr_state)
    aggregate = await phases.reduce_attribute(context, spec, candidates, attr_state)
    validated = await phases.validate_attribute(context, spec, aggregate, len(map_chunks), attr_state)
    return await phases.threshold_and_persist(
        context,
        spec,
        validated,
        candidates,
        len(map_chunks),
        attr_state,
    )


async def _process_attributes(
    context: ExtractionContext,
    attribute_specs: Sequence[AttributeSpec],
) -> dict[str, AttributeResult]:
    results: dict[str, AttributeResult] = {}
    for spec in attribute_specs:
        result = await _process_attribute(context, spec)
        results[spec.name] = result
    return results


async def run_extraction(
    session: AsyncSession,
    request: ExtractionRequest,
    *,
    emit: BrokerCallback | None = None,
    job: ExtractionJob | None = None,
) -> ExtractionResult:
    if request.tenant_id is None:
        msg = 'tenant_id must be specified for extraction requests'
        raise ValueError(msg)

    settings = get_settings()
    retrieval_config = resolve_execution_config(settings, request)

    job = await _prepare_job(session, request, job, retrieval_config, settings)
    if job.status == ExtractionJobStatus.CANCELED:
        cancel_msg = job.error or 'canceled by user'
        return ExtractionResult.from_job(job, error_msg=cancel_msg)

    attribute_specs = get_attribute_specs(request.doc_type, request.attributes)
    progress = ProgressTracker(total_attributes=len(attribute_specs))
    states = {spec.name: AttributeState(spec.name) for spec in attribute_specs}

    context = build_extraction_context(
        session=session,
        request=request,
        job=job,
        retrieval_config=retrieval_config,
        digest=job.document_digest,
        collection_name=job.collection_name,
        model_name=job.model,
        emit=emit,
        progress=progress,
        attribute_states=states,
    )

    await context.emitter.emit(StatusEvent.JOB_STARTED, include_snapshot=True)

    errors: list[str] = []
    results: dict[str, AttributeResult] = {}

    try:
        results = await _process_attributes(context, attribute_specs)

        job = await update_job_status(session, job, status=ExtractionJobStatus.COMPLETED)
        await context.emitter.emit(
            StatusEvent.JOB_COMPLETED,
            status_override=ExtractionJobStatus.COMPLETED,
            include_snapshot=True,
            results={
                name: {
                    'value': result.value,
                    'confidence': result.confidence,
                    'provenance': list(result.provenance),
                }
                for name, result in results.items()
            },
        )
    except ExtractionCancelledError:
        cancel_msg = 'canceled by user'
        errors.append(cancel_msg)
        job = await update_job_status(
            session,
            job,
            status=ExtractionJobStatus.CANCELED,
            error=cancel_msg,
        )
        await context.emitter.emit(
            StatusEvent.JOB_CANCELED,
            status_override=ExtractionJobStatus.CANCELED,
            errors=errors,
            include_snapshot=True,
        )
    except Exception as exc:  # noqa: BLE001 - capture & propagate
        errors.append(str(exc))
        await update_job_status(session, job, status=ExtractionJobStatus.FAILED, error=str(exc))
        await context.emitter.emit(
            StatusEvent.JOB_FAILED,
            status_override=ExtractionJobStatus.FAILED,
            errors=errors,
            include_snapshot=True,
        )
        raise

    return ExtractionResult.from_job(job, attributes=results, error_msg=errors)


def build_extraction_graph() -> Callable[[AsyncSession, ExtractionRequest], Awaitable[ExtractionResult]]:
    async def _runner(session: AsyncSession, request: ExtractionRequest) -> ExtractionResult:
        return await run_extraction(session, request)

    return _runner


__all__ = ['run_extraction', 'build_extraction_graph']
