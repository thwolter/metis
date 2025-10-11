from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import dramatiq
from loguru import logger

from agent.graph import graph
from agent.schemas import ContextSchema, MetadataSchema
from core.db import session_scope
from metadata.models import Job, JobStatus
from metadata.service import (
    merge_metadata,
    metadata_fingerprint,
    record_metadata_version,
    update_vecstore_metadata,
)


def _load_job(job_id: UUID) -> tuple[Job, ContextSchema, MetadataSchema | None, list[str]]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise LookupError(f'Job {job_id} not found')
        if job.status in {JobStatus.SUCCEEDED, JobStatus.CANCELED}:
            raise LookupError(f'Job {job_id} already in terminal status {job.status}')
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.error_type = None
        job.error_msg = None
        session.add(job)
        session.flush()
        context = ContextSchema.model_validate(job.context)
        base_metadata = (
            MetadataSchema.model_validate(job.input_metadata)
            if isinstance(job.input_metadata, dict) and job.input_metadata
            else None
        )
        locked_fields = list(job.locked_fields)
    return job, context, base_metadata, locked_fields


def _run_agent(context: ContextSchema) -> MetadataSchema | None:
    try:
        result = graph.invoke({}, config={'configurable': context.model_dump()})
    except Exception:  # pragma: no cover - external dependency
        logger.exception('Metadata agent failed: context=%s', context)
        raise

    if isinstance(result, MetadataSchema):
        return result
    if isinstance(result, dict):
        return MetadataSchema.model_validate(result)
    return MetadataSchema.model_validate(result or {})


def _finalise_success(
    job_id: UUID,
    *,
    metadata: MetadataSchema,
    fingerprint: str,
) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.warning('Job %s disappeared before completion', job_id)
            return
        if job.status == JobStatus.CANCELED:
            logger.info('Job %s was canceled; skip result persistence', job_id)
            return

        record_metadata_version(
            session,
            document_id=job.document_id,
            metadata=metadata,
            fingerprint=fingerprint,
        )

        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(timezone.utc)
        job.processing_fingerprint = fingerprint
        session.add(job)


def _finalise_failure(job_id: UUID, exc: Exception) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        job.retries += 1
        job.error_type = exc.__class__.__name__
        job.error_msg = str(exc)
        session.add(job)


def _process_job(job_id: UUID) -> None:
    try:
        job, context, base_metadata, locked_fields = _load_job(job_id)
    except LookupError as exc:  # pragma: no cover - defensive
        logger.warning(str(exc))
        return

    document_id = job.document_id
    metadata_candidate: MetadataSchema | None = None
    try:
        metadata_candidate = _run_agent(context)
        merged = merge_metadata(
            base=base_metadata,
            generated=metadata_candidate,
            locked_fields=locked_fields,
        )
        fingerprint = metadata_fingerprint(merged)
        update_vecstore_metadata(context, document_id, merged)
        _finalise_success(job.job_id, metadata=merged, fingerprint=fingerprint)
    except Exception as exc:  # noqa: BLE001 - capture all failures for job bookkeeping
        if metadata_candidate is None:
            logger.exception('Job %s failed during metadata generation', job_id)
        else:
            logger.exception('Job %s failed during persistence', job_id)
        _finalise_failure(job_id, exc)


@dramatiq.actor
def process_metadata_job(job_id: str) -> None:
    _process_job(UUID(job_id))


def enqueue_job(job_id: UUID) -> None:
    process_metadata_job.send(str(job_id))
