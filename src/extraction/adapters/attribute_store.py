from __future__ import annotations

from datasifter.interfaces import AttributeStore as AttributeStoreInterface
from datasifter.schemas import AttributeResult, AttributeSpec, JobState
from sqlmodel.ext.asyncio.session import AsyncSession

from extraction.models import ExtractionJob
from extraction.service import persist_attribute


class AttributeStore(AttributeStoreInterface):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _ensure_model(self, job: JobState) -> ExtractionJob:
        model = job.context.get('orm')
        if isinstance(model, ExtractionJob):
            return model
        model = await self._session.get(ExtractionJob, job.job_id)
        if model is None:
            msg = f'ExtractionJob {job.job_id} not found'
            raise RuntimeError(msg)
        job.context['orm'] = model
        return model

    async def persist(self, job: JobState, spec: AttributeSpec, result: AttributeResult) -> None:
        model = await self._ensure_model(job)
        await persist_attribute(
            self._session,
            tenant_id=model.tenant_id,
            job=model,
            result=result,
            spec=spec,
        )
