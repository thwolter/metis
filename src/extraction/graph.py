from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from core.config import get_settings
from extraction.map_step import MapExtractor
from extraction.models import ExtractionJob, ExtractionJobStatus
from extraction.persistence import (
    create_extraction_job,
    increment_sequence,
    persist_attribute,
    update_job_status,
)
from extraction.reduce_step import reduce_candidates
from extraction.registry import get_attribute_specs
from extraction.retrieval import retrieve_chunks
from extraction.schemas import (
    AttributeProgress,
    AttributeResult,
    Candidate,
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatusPayload,
    ProgressSnapshot,
    RetrievalConfig,
    RetrievedChunk,
    StatusEvent,
    Thresholds,
)
from extraction.thresholds import abstain_output, passes_thresholds
from extraction.validate import apply_validation
from metadata.models import utc_now


class ExtractionCancelledError(Exception):
    """Raised when an extraction job is canceled."""


BrokerCallback = Callable[[UUID, dict[str, Any]], Awaitable[None]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProgressTracker:
    total_attributes: int
    attributes_done: int = 0
    map_calls_planned: int = 0
    map_calls_done: int = 0
    reduce_done: int = 0
    validated: int = 0
    persisted: int = 0

    def snapshot(self) -> ProgressSnapshot:
        return ProgressSnapshot(
            attributes_total=self.total_attributes,
            attributes_done=self.attributes_done,
            map_calls_planned=self.map_calls_planned,
            map_calls_done=self.map_calls_done,
            reduce_done=self.reduce_done,
            validated=self.validated,
            persisted=self.persisted,
        )


@dataclass
class AttributeState:
    name: str
    state: str = 'pending'
    confidence: float | None = None
    mapped: int = 0
    planned: int = 0

    def to_progress(self) -> AttributeProgress:
        return AttributeProgress(
            name=self.name,
            state=self.state,
            confidence=self.confidence,
            mapped=self.mapped or None,
            planned=self.planned or None,
        )


class StatusEmitter:
    def __init__(
        self,
        session: AsyncSession,
        *,
        job,
        doc_id,
        doc_type: str,
        callback: BrokerCallback | None,
        progress: ProgressTracker,
        attribute_states: dict[str, AttributeState],
    ):
        self._session = session
        self._job = job
        self._doc_id = doc_id
        self._doc_type = doc_type
        self._callback = callback
        self._progress = progress
        self._attribute_states = attribute_states
        self._lock = asyncio.Lock()

    async def emit(
        self,
        event: StatusEvent,
        *,
        status_override: str | None = None,
        attribute_payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        summary: str | None = None,
        errors: list[str] | None = None,
        include_snapshot: bool = False,
        results: dict[str, Any] | None = None,
    ) -> ExtractionStatusPayload:
        async with self._lock:
            seq = await increment_sequence(self._session, self._job)
            status_text = status_override or self._job.status.value
            payload = ExtractionStatusPayload(
                seq=seq,
                timestamp=_utcnow(),
                job_id=self._job.job_id,
                doc_id=self._doc_id,
                doc_type=self._doc_type,
                event=event,
                status=status_text,
                progress=self._progress.snapshot() if include_snapshot else None,
                attribute=attribute_payload,
                provenance=provenance,
                summary=summary,
                errors=errors,
                attributes=[state.to_progress() for state in self._attribute_states.values()]
                if include_snapshot
                else None,
                results=results,
            )
            if self._callback is not None:
                await self._callback(self._job.job_id, payload.model_dump(mode='json'))
            return payload


def _default_thresholds() -> Thresholds:
    return Thresholds(min_confidence=0.65, min_chunks=1)


def _resolve_execution_config(
    settings,
    request: ExtractionRequest,
) -> tuple[RetrievalConfig, str, str]:
    if request.retriever is None:
        retrieval_config = RetrievalConfig(
            max_chunks=getattr(settings, 'extraction_max_chunks', 6),
            top_m=getattr(settings, 'extraction_top_m', 3),
            header_boost=getattr(settings, 'extraction_header_boost', 0.5),
            semantic_weight=1.0,
            bm25_weight=0.5,
            hints_weight=0.3,
        )
    else:
        retrieval_config = request.retriever
    model_name = request.model or getattr(settings, 'extraction_default_model', 'openai:gpt-4o-mini')
    model_version = getattr(settings, 'extraction_model_version', 'unversioned')
    return retrieval_config, model_name, model_version


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
    retrieval_config, model_name, model_version = _resolve_execution_config(settings, request)

    digest = request.digest
    collection_name = request.collection_name
    if job is not None:
        digest = job.document_digest
        collection_name = job.collection_name
    if digest is None or collection_name is None:
        msg = 'digest and collection_name must be provided for extraction'
        raise ValueError(msg)

    retriever_snapshot = retrieval_config.model_dump(mode='json')
    if job is None:
        job = await create_extraction_job(
            session,
            tenant_id=request.tenant_id,
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
        if request.model:
            job.model = model_name
        else:
            model_name = job.model
        if job.model_version:
            model_version = job.model_version
        else:
            job.model_version = model_version
        job.retriever_config = retriever_snapshot
        job.options = {'dry_run': request.dry_run}
        session.add(job)

    if job.status == ExtractionJobStatus.CANCELED:
        cancel_msg = job.error or 'canceled by user'
        return ExtractionResult(
            job_id=job.job_id,
            doc_id=request.doc_id,
            doc_type=request.doc_type,
            attributes={},
            model=model_name,
            model_version=model_version,
            started_at=job.started_at or utc_now(),
            completed_at=job.finished_at,
            errors=[cancel_msg],
        )

    job = await update_job_status(session, job, status=ExtractionJobStatus.RUNNING)
    map_extractor = MapExtractor(model=model_name)

    attribute_specs = get_attribute_specs(request.doc_type, request.attributes)
    progress = ProgressTracker(total_attributes=len(attribute_specs))
    states = {spec.name: AttributeState(spec.name) for spec in attribute_specs}

    emitter = StatusEmitter(
        session,
        job=job,
        doc_id=request.doc_id,
        doc_type=request.doc_type,
        callback=emit,
        progress=progress,
        attribute_states=states,
    )

    async def ensure_active() -> None:
        await session.refresh(job)
        if job.status == ExtractionJobStatus.CANCELED:
            raise ExtractionCancelledError()

    await emitter.emit(StatusEvent.JOB_STARTED, include_snapshot=True)

    results: dict[str, AttributeResult] = {}
    errors: list[str] = []

    try:
        for spec in attribute_specs:
            await ensure_active()
            attr_state = states[spec.name]
            attr_state.state = 'mapping'
            await emitter.emit(
                StatusEvent.ATTRIBUTE_STARTED,
                attribute_payload={'name': spec.name, 'phase': 'retrieve'},
                include_snapshot=True,
            )

            chunks: Sequence[RetrievedChunk] = await retrieve_chunks(
                session,
                tenant_id=request.tenant_id,
                collection_name=collection_name,
                digest=digest,
                doc_type=request.doc_type,
                attribute=spec,
                config=retrieval_config,
            )

            if retrieval_config.top_m and retrieval_config.top_m < len(chunks):
                map_chunks = list(chunks[: retrieval_config.top_m])
            else:
                map_chunks = list(chunks)

            attr_state.planned = len(map_chunks)
            progress.map_calls_planned += len(map_chunks)

            candidates: list[Candidate] = []
            for chunk in map_chunks:
                await ensure_active()
                candidate = await map_extractor.extract_candidate(
                    doc_type=request.doc_type,
                    attribute=spec,
                    chunk=chunk,
                    attempt=len(candidates) + 1,
                )
                candidates.append(candidate)
                attr_state.mapped += 1
                progress.map_calls_done += 1
                await emitter.emit(
                    StatusEvent.CHUNK_MAPPED,
                    attribute_payload={
                        'name': spec.name,
                        'phase': 'map',
                        'retrieval': candidate.retrieval.model_dump(mode='json'),
                        'candidate': {
                            'value': candidate.value,
                            'confidence_local': candidate.confidence_local,
                            'rationale': candidate.rationale,
                        },
                    },
                )

            aggregate = reduce_candidates(candidates)
            progress.reduce_done += 1
            attr_state.state = 'reduced'
            attr_state.confidence = aggregate.confidence
            await ensure_active()
            await emitter.emit(
                StatusEvent.ATTRIBUTE_REDUCED,
                attribute_payload={
                    'name': spec.name,
                    'phase': 'reduce',
                    'aggregate': {
                        'value': aggregate.value,
                        'confidence': aggregate.confidence,
                        'provenance': list(aggregate.provenance),
                        'supporting': [cand.raw_json for cand in aggregate.supporting_candidates],
                    },
                },
            )

            validated = apply_validation(
                attribute=spec,
                value=aggregate.value,
                confidence=aggregate.confidence,
                chunk_count=len(map_chunks),
                provenance=aggregate.provenance,
            )
            progress.validated += 1
            attr_state.state = 'validated'
            attr_state.confidence = validated.confidence

            await ensure_active()
            await emitter.emit(
                StatusEvent.ATTRIBUTE_VALIDATED,
                attribute_payload={
                    'name': spec.name,
                    'phase': 'validate',
                    'value': validated.value,
                    'issues': [issue.model_dump() for issue in validated.validation_issues],
                },
            )

            thresholds = spec.thresholds or _default_thresholds()
            passes = passes_thresholds(validated, thresholds, len(map_chunks))
            attr_state.state = 'thresholded'
            decision = 'accept' if passes else 'abstain'
            await ensure_active()
            await emitter.emit(
                StatusEvent.ATTRIBUTE_THRESHOLDED,
                attribute_payload={
                    'name': spec.name,
                    'phase': 'threshold',
                    'decision': decision,
                    'thresholds': thresholds.model_dump(),
                },
            )

            if not passes or request.dry_run:
                result = abstain_output(spec.name, candidates)
                results[spec.name] = result
                if not passes:
                    attr_state.state = 'abstained'
                else:
                    attr_state.state = 'persisted'
                progress.attributes_done += 1
                await ensure_active()
                await emitter.emit(
                    StatusEvent.ATTRIBUTE_PERSISTED,
                    attribute_payload={
                        'name': spec.name,
                        'phase': 'persist',
                        'value': result.value,
                        'confidence': result.confidence,
                        'status': result.status,
                    },
                    include_snapshot=True,
                )
                continue

            record = await persist_attribute(
                session,
                tenant_id=request.tenant_id,
                job=job,
                result=validated,
                spec=spec,
            )
            progress.persisted += 1
            progress.attributes_done += 1
            attr_state.state = 'persisted'
            attr_state.confidence = validated.confidence
            results[spec.name] = validated
            await ensure_active()
            await emitter.emit(
                StatusEvent.ATTRIBUTE_PERSISTED,
                attribute_payload={
                    'name': spec.name,
                    'phase': 'persist',
                    'value': record.value_json,
                    'confidence': record.confidence,
                    'status': validated.status,
                },
                include_snapshot=True,
            )

        job = await update_job_status(session, job, status=ExtractionJobStatus.COMPLETED)
        await emitter.emit(
            StatusEvent.JOB_COMPLETED,
            status_override='completed',
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
        await emitter.emit(
            StatusEvent.JOB_CANCELED,
            status_override='canceled',
            errors=errors,
            include_snapshot=True,
        )
    except Exception as exc:  # noqa: BLE001 - capture & propagate
        errors.append(str(exc))
        job = await update_job_status(session, job, status=ExtractionJobStatus.FAILED, error=str(exc))
        await emitter.emit(
            StatusEvent.JOB_FAILED,
            status_override='failed',
            errors=errors,
            include_snapshot=True,
        )
        raise

    return ExtractionResult(
        job_id=job.job_id,
        doc_id=request.doc_id,
        doc_type=request.doc_type,
        attributes=results,
        model=model_name,
        model_version=model_version,
        started_at=job.started_at or utc_now(),
        completed_at=job.finished_at,
        errors=errors,
    )


def build_extraction_graph() -> Callable[[AsyncSession, ExtractionRequest], Awaitable[ExtractionResult]]:
    async def _runner(session: AsyncSession, request: ExtractionRequest) -> ExtractionResult:
        return await run_extraction(session, request)

    return _runner
