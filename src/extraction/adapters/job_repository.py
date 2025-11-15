from __future__ import annotations

from uuid import UUID

from datasifter import (
    ExtractionRequest,
    JobState,
    JobStatus,
    RetrievalConfig,
    SqlModelJobRepository,
)
from datasifter.interfaces import JobRepository as JobRepositoryInterface
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import ExtractionJob, ExtractionJobStatus
from ..service import create_extraction_job, increment_sequence, update_job_status
from ..utils import job_state_from_model


def _status_from_model(status: ExtractionJobStatus) -> JobStatus:
    return JobStatus(status.value)


async def _resolve_tenant(*, request: ExtractionRequest, existing: ExtractionJob | None) -> UUID:
    if existing:
        return existing.tenant_id
    if request.tenant_id is None:
        msg = 'tenant_id must be provided for extraction jobs'
        raise ValueError(msg)
    return request.tenant_id


class _JobRepository(JobRepositoryInterface):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _ensure_model(self, state: JobState) -> ExtractionJob:
        model = state.context.get('orm')
        if isinstance(model, ExtractionJob):
            return model
        model = await self._session.get(ExtractionJob, state.job_id)
        if model is None:
            msg = f'ExtractionJob {state.job_id} not found'
            raise RuntimeError(msg)
        state.context['orm'] = model
        return model

    async def prepare_job(
        self,
        *,
        request: ExtractionRequest,
        job: JobState | None,
        retrieval_config: RetrievalConfig,
        model_name: str,
        model_version: str,
    ) -> JobState:
        existing_model = await self._ensure_model(job) if job is not None else None
        tenant_id = await _resolve_tenant(request=request, existing=existing_model)
        retriever_snapshot = retrieval_config.model_dump(mode='json')

        if existing_model is None:
            if request.digest is None or request.collection_name is None:
                msg = 'digest and collection_name must be provided for extraction'
                raise ValueError(msg)
            new_job = await create_extraction_job(
                self._session,
                tenant_id=tenant_id,
                doc_id=request.doc_id,
                doc_type=request.doc_type,
                model=model_name,
                model_version=model_version,
                retriever_config=retriever_snapshot,
                options={'dry_run': request.dry_run},
                document_digest=request.digest,
                collection_name=request.collection_name,
            )
            prepared = await update_job_status(self._session, new_job, status=ExtractionJobStatus.RUNNING)
            return job_state_from_model(prepared)

        updated = existing_model
        if updated.model != model_name:
            updated.model = model_name
        if updated.model_version != model_version:
            updated.model_version = model_version
        updated.retriever_config = retriever_snapshot
        updated.options = {'dry_run': request.dry_run}
        if request.digest is not None:
            updated.document_digest = request.digest
        if request.collection_name is not None:
            updated.collection_name = request.collection_name
        self._session.add(updated)
        await self._session.flush()
        await self._session.refresh(updated)
        prepared = await update_job_status(self._session, updated, status=ExtractionJobStatus.RUNNING)
        return job_state_from_model(prepared, base=job)

    async def update_status(
        self,
        job: JobState,
        *,
        status: JobStatus,
        error: str | None = None,
    ) -> JobState:
        model = await self._ensure_model(job)
        target_status = ExtractionJobStatus(status.value)
        updated = await update_job_status(self._session, model, status=target_status, error=error)
        return job_state_from_model(updated, base=job)

    async def refresh(self, job: JobState) -> JobState:
        model = await self._ensure_model(job)
        await self._session.refresh(model)
        return job_state_from_model(model, base=job)

    async def increment_sequence(self, job: JobState) -> int:
        model = await self._ensure_model(job)
        seq = await increment_sequence(self._session, model)
        job.seq = seq
        return seq


def _status_to_model(status: JobStatus) -> ExtractionJobStatus:
    return ExtractionJobStatus(status.value)


class JobRepository(SqlModelJobRepository[ExtractionJob, ExtractionJobStatus]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session=session,
            job_model=ExtractionJob,
            status_factory=_status_to_model,
            create_job=create_extraction_job,
            update_job_status=update_job_status,
            increment_sequence=increment_sequence,
            # optional: override tenant_resolver / options_builder if needed
        )
