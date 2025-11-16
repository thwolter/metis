from __future__ import annotations

from datasifter import (
    JobStatus,
    SqlModelJobRepository,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import ExtractionJob, ExtractionJobStatus
from ..service import create_extraction_job, increment_sequence, update_job_status


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
        )
