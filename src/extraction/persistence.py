from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from extraction.registry.registry import AttributeSpec
from metadata.service import ensure_document
from utils import utc_now

from .models import ExtractedAttribute, ExtractionJob, ExtractionJobStatus
from .schemas import AttributeResult


async def create_extraction_job(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    doc_id: UUID,
    doc_type: str,
    model: str,
    model_version: str,
    retriever_config: dict[str, Any] | None,
    options: dict[str, Any] | None,
    document_digest: str,
    collection_name: str,
) -> ExtractionJob:
    await ensure_document(session, tenant_id=tenant_id, document_id=doc_id)
    job = ExtractionJob(
        tenant_id=tenant_id,
        doc_id=doc_id,
        doc_type=doc_type,
        model=model,
        model_version=model_version,
        retriever_config=retriever_config,
        options=options,
        document_digest=document_digest,
        collection_name=collection_name,
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)
    return job


async def update_job_status(
    session: AsyncSession,
    job: ExtractionJob,
    status: ExtractionJobStatus,
    error: str | None = None,
) -> ExtractionJob:
    job.status = status
    if status == ExtractionJobStatus.RUNNING and job.started_at is None:
        job.started_at = utc_now()
    if status in {
        ExtractionJobStatus.COMPLETED,
        ExtractionJobStatus.FAILED,
        ExtractionJobStatus.CANCELED,
    }:
        job.finished_at = utc_now()
    job.error = error
    session.add(job)
    await session.flush()
    await session.refresh(job)
    return job


async def increment_sequence(session: AsyncSession, job: ExtractionJob) -> int:
    job.seq += 1
    session.add(job)
    await session.flush()
    return job.seq


async def persist_attribute(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    job: ExtractionJob,
    result: AttributeResult,
    spec: AttributeSpec,
) -> ExtractedAttribute:
    stmt = select(ExtractedAttribute).where(
        ExtractedAttribute.job_id == job.job_id,
        ExtractedAttribute.attribute == result.name,
    )
    existing = (await session.exec(stmt)).first()

    value_payload: dict[str, Any] | None
    if result.value is None and not result.validation_issues:
        value_payload = None
    else:
        value_payload = {
            'value': result.value,
            'status': result.status,
            'rationale': result.rationale,
            'validation_issues': [issue.model_dump() for issue in result.validation_issues],
        }

    if existing is None:
        record = ExtractedAttribute(
            tenant_id=tenant_id,
            job_id=job.job_id,
            doc_id=job.doc_id,
            attribute=result.name,
            value_json=value_payload,
            confidence=result.confidence,
            provenance=list(result.provenance),
            model_version=job.model_version,
            constraints_snapshot=spec.model_dump(mode='json'),
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record

    existing.value_json = value_payload
    existing.confidence = result.confidence
    existing.provenance = list(result.provenance)
    existing.model_version = job.model_version
    existing.constraints_snapshot = spec.model_dump(mode='json')
    session.add(existing)
    await session.flush()
    await session.refresh(existing)
    return existing
