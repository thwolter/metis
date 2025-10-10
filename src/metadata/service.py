from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from typing import Sequence
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from agent.schemas import ContextSchema, MetadataSchema
from metadata.models import DocumentMetadata, Job, JobStatus
from metadata.schemas import CreateJobDTO
from utils.vstore import get_collection_uuid, pg_connect

logger = logging.getLogger(__name__)


def _metadata_to_dict(metadata: MetadataSchema | None) -> dict:
    if metadata is None:
        return {}
    return metadata.model_dump(mode='json')


def _locked_fields(metadata: MetadataSchema | None) -> list[str]:
    if metadata is None:
        return []
    return [name for name, value in metadata.model_dump().items() if value is not None]


def _job_lookup(session: Session, *, job: Job) -> Job:
    stmt = select(Job).where(
        Job.tenant_id == job.tenant_id,
        Job.document_id == job.document_id,
        Job.profile == job.profile,
        Job.ingestion_fingerprint == job.ingestion_fingerprint,
    )
    existing = session.exec(stmt).one()
    return existing


def create_job(session: Session, dto: CreateJobDTO) -> Job:
    """Create or return an idempotent metadata job."""
    document_id = dto.resolved_document_id()
    ingestion_fingerprint = dto.idempotency_key or dto.context.digest

    job = Job(
        tenant_id=dto.context.tenant_id,
        document_id=document_id,
        profile=dto.profile,
        ingestion_fingerprint=ingestion_fingerprint,
        priority=dto.priority,
        callback_url=str(dto.callback_url) if dto.callback_url else None,
        idempotency_key=dto.idempotency_key,
        input_metadata=_metadata_to_dict(dto.metadata),
        locked_fields=_locked_fields(dto.metadata),
        context=dto.context.model_dump(mode='json'),
    )

    session.add(job)
    try:
        session.commit()
        session.refresh(job)
        session.expunge(job)
        logger.info('Created job %s for document %s', job.job_id, job.document_id)
        return job
    except IntegrityError:
        session.rollback()
        existing = _job_lookup(session, job=job)
        logger.info('Reusing job %s for document %s', existing.job_id, existing.document_id)
        session.expunge(existing)
        return existing


def get_job(session: Session, job_id: UUID) -> Job | None:
    return session.get(Job, job_id)


def cancel_job(session: Session, job: Job) -> Job:
    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
        return job
    job.status = JobStatus.CANCELED
    job.finished_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()
    session.refresh(job)
    session.expunge(job)
    return job


def merge_metadata(
    *,
    base: MetadataSchema | None,
    generated: MetadataSchema | None,
    locked_fields: Sequence[str],
) -> MetadataSchema:
    base_data = base.model_dump() if isinstance(base, MetadataSchema) else {}
    generated_data = generated.model_dump() if isinstance(generated, MetadataSchema) else {}

    merged = base_data.copy()
    for key, value in generated_data.items():
        if key in locked_fields and key in base_data and base_data[key] is not None:
            continue
        if value is not None:
            merged[key] = value
        else:
            merged.setdefault(key, None)

    for key in locked_fields:
        if key in base_data:
            merged[key] = base_data[key]

    return MetadataSchema.model_validate(merged)


def next_metadata_version(session: Session, document_id: UUID) -> int:
    stmt = select(DocumentMetadata.version).where(DocumentMetadata.document_id == document_id)
    versions = session.exec(stmt).all()
    return max(versions, default=0) + 1


def metadata_fingerprint(metadata: MetadataSchema) -> str:
    payload = metadata.model_dump(mode='json', by_alias=True, exclude_none=False)
    normalised = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return sha256(normalised.encode('utf-8')).hexdigest()


def record_metadata_version(
    session: Session,
    *,
    document_id: UUID,
    metadata: MetadataSchema,
    fingerprint: str | None = None,
) -> DocumentMetadata:
    version = next_metadata_version(session, document_id)
    fingerprint = fingerprint or metadata_fingerprint(metadata)
    record = DocumentMetadata(
        document_id=document_id,
        version=version,
        fingerprint=fingerprint,
        payload=metadata.model_dump(mode='json'),
    )
    session.add(record)
    session.flush()
    return record


@contextmanager
def _vectorstore_connection(tenant_id: UUID):
    conn = pg_connect(tenant_id)
    try:
        yield conn
    finally:
        conn.close()


def update_vecstore_metadata(context: ContextSchema, document_id: UUID, metadata: MetadataSchema) -> None:
    """Update meta/tags fields in vecstore.chunks for the given document."""
    metadata_dict = metadata.model_dump(mode='json', exclude_none=True)
    tags = metadata_dict.get('tags') or []
    meta_payload = json.dumps(metadata_dict)
    tags_payload = json.dumps(tags)

    try:
        with _vectorstore_connection(context.tenant_id) as conn:
            collection_uuid = get_collection_uuid(conn, context.collection_name)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE vecstore.chunks
                    SET meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb,
                        tags = %s::jsonb
                    WHERE collection_id = %s::uuid
                      AND document_id = %s::uuid
                    """,
                    (meta_payload, tags_payload, str(collection_uuid), str(document_id)),
                )
            conn.commit()
    except Exception:  # noqa: BLE001 - best-effort update, log only
        logger.exception('Failed updating vecstore metadata for document %s', document_id)


def fetch_document_metadata(
    session: Session,
    *,
    document_id: UUID,
    version: str | None,
) -> DocumentMetadata | None:
    stmt = select(DocumentMetadata).where(DocumentMetadata.document_id == document_id)

    if version is None or version == 'latest':
        stmt = stmt.order_by(desc(DocumentMetadata.version))
        result = session.exec(stmt)
        record = result.first()
        if record is not None:
            session.expunge(record)
        return record

    if version.lower().startswith('v'):
        version_num = version[1:]
    else:
        version_num = version

    try:
        version_int = int(version_num)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid version specifier: {version!r}') from exc

    stmt = stmt.where(DocumentMetadata.version == version_int)
    result = session.exec(stmt)
    record = result.first()
    if record is not None:
        session.expunge(record)
    return record
