from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from hashlib import sha256
from typing import Sequence
from uuid import UUID

from psycopg2 import sql
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.schemas import AccessContext

from agent.schemas import ContextSchema, MetadataSchema
from core.config import get_settings
from core.db import scoped_session
from core.logging import configure_logging
from metadata.models import DocumentMetadata, Job, JobStatus, utc_now
from metadata.schemas import CreateJobDTO
from utils.vstore import get_collection_uuid, pg_connect

configure_logging()

logger = logging.getLogger(__name__)
settings = get_settings()


def _fingerprint_from_payload(payload: dict) -> str:
    normalised = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return sha256(normalised.encode('utf-8')).hexdigest()


def _metadata_to_dict(metadata: MetadataSchema | None) -> dict:
    if metadata is None:
        return {}
    return metadata.model_dump(mode='json')


def _locked_fields(metadata: MetadataSchema | None, explicit: list[str] | None) -> list[str]:
    if explicit is not None:
        return list(explicit)
    return []


async def _job_lookup(job: Job, *, access_context: AccessContext) -> Job:
    stmt = select(Job).where(
        Job.tenant_id == job.tenant_id,
        Job.document_id == job.document_id,
        Job.profile == job.profile,
        Job.ingestion_fingerprint == job.ingestion_fingerprint,
    )
    async with scoped_session(access_context=access_context) as session:
        result = await session.exec(stmt)
        existing = result.first()
    if existing is None:
        raise LookupError('Job not found for idempotent lookup')
    return existing


async def create_job(session: AsyncSession, dto: CreateJobDTO, *, access_context: AccessContext) -> Job:
    """Create or return an idempotent metadata job."""
    document_id = dto.resolved_document_id()
    ingestion_fingerprint = dto.idempotency_key or dto.context.digest
    tenant_id = access_context.tenant_id

    job = Job(
        tenant_id=tenant_id,
        user_id=access_context.user_id,
        document_id=document_id,
        profile=dto.profile,
        ingestion_fingerprint=ingestion_fingerprint,
        priority=dto.priority,
        callback_url=str(dto.callback_url) if dto.callback_url else None,
        idempotency_key=dto.idempotency_key,
        input_metadata=_metadata_to_dict(dto.metadata),
        locked_fields=_locked_fields(dto.metadata, dto.locked_fields),
        document_digest=dto.context.digest,
        collection_name=dto.context.collection_name,
    )

    session.add(job)
    try:
        await session.commit()
        await session.refresh(job)
        session.expunge(job)
        logger.info('Created job %s for document %s', job.job_id, job.document_id)
        return job
    except IntegrityError:
        await session.rollback()
        existing = await _job_lookup(job, access_context=access_context)
        logger.info('Reusing job %s for document %s', existing.job_id, existing.document_id)
        return existing
    except Exception:
        await session.rollback()
        raise


async def get_job(session: AsyncSession, job_id: UUID) -> Job | None:
    return await session.get(Job, job_id)


async def cancel_job(session: AsyncSession, job: Job) -> Job:
    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
        return job
    job.status = JobStatus.CANCELED
    job.finished_at = utc_now()
    session.add(job)
    await session.commit()
    await session.refresh(job)
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


async def next_metadata_version(session: AsyncSession, tenant_id: UUID, document_id: UUID) -> int:
    stmt = select(func.max(DocumentMetadata.version)).where(
        DocumentMetadata.tenant_id == tenant_id,
        DocumentMetadata.document_id == document_id,
    )
    result = await session.exec(stmt)
    current = result.one_or_none()
    return (current or 0) + 1


def metadata_fingerprint(metadata: MetadataSchema) -> str:
    payload = metadata.model_dump(mode='json', by_alias=True, exclude_none=False)
    return _fingerprint_from_payload(payload)


async def record_metadata_version(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    metadata: MetadataSchema | None,
    fingerprint: str | None = None,
) -> DocumentMetadata:
    version = await next_metadata_version(session, tenant_id, document_id)

    if metadata is None:
        payload = {}  # empty payload when metadata is missing
        fp = fingerprint or _fingerprint_from_payload(payload)
    else:
        payload = metadata.model_dump(mode='json')
        fp = fingerprint or metadata_fingerprint(metadata)

    record = DocumentMetadata(
        tenant_id=tenant_id,
        document_id=document_id,
        version=version,
        fingerprint=fp,
        payload=payload,
    )
    session.add(record)
    await session.flush()
    return record


async def fetch_document_metadata(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    version: str | None,
) -> DocumentMetadata | None:
    stmt = select(DocumentMetadata).where(
        DocumentMetadata.tenant_id == tenant_id,
        DocumentMetadata.document_id == document_id,
    )

    if version is None or version == 'latest':
        stmt = stmt.order_by(desc('version'))
        result = await session.exec(stmt)
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
    result = await session.exec(stmt)
    record = result.first()
    if record is not None:
        session.expunge(record)
    return record


async def manual_metadata_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    metadata: MetadataSchema,
) -> DocumentMetadata:
    """Persist a manual metadata version, skipping agent processing."""
    fingerprint = metadata_fingerprint(metadata)
    existing = await fetch_document_metadata(session, tenant_id=tenant_id, document_id=document_id, version='latest')
    if existing and existing.fingerprint == fingerprint:
        return existing

    record = await record_metadata_version(
        session,
        tenant_id=tenant_id,
        document_id=document_id,
        metadata=metadata,
        fingerprint=fingerprint,
    )
    await session.commit()
    await session.refresh(record)
    session.expunge(record)
    return record


@contextmanager
def _vectorstore_connection(tenant_id: UUID):
    conn = pg_connect(tenant_id)
    try:
        yield conn
    finally:
        conn.close()


def update_vecstore_metadata(context: ContextSchema, document_id: UUID, metadata: MetadataSchema) -> None:
    """Update cmetadata for the given document inside langchain_pg_embedding."""
    metadata_dict = metadata.model_dump(mode='json', exclude_none=True)
    metadata_dict['digest'] = context.digest
    meta_payload = json.dumps(metadata_dict)

    try:
        with _vectorstore_connection(context.tenant_id) as conn:
            collection_uuid = get_collection_uuid(conn, context.collection_name)
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        UPDATE {}.langchain_pg_embedding
                        SET cmetadata = COALESCE(cmetadata, '{{}}'::jsonb) || %s::jsonb
                        WHERE collection_id = %s::uuid
                          AND cmetadata ->> 'digest' = %s
                        """
                    ).format(sql.Identifier(settings.pg_vector_schema)),
                    (meta_payload, str(collection_uuid), context.digest),
                )
            conn.commit()
    except Exception as e:  # noqa: BLE001 - best-effort update, log only
        logger.exception(f'Failed updating vecstore metadata for document {document_id}: {str(e)}')
