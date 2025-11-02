from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
from typing import Sequence
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.schemas import AccessContext

from agent.schemas import ContextSchema, MetadataSchema
from core.config import get_settings
from core.db import pg_connect, scoped_session
from core.logging import configure_logging
from metadata.models import Document, DocumentMetadata, Job, JobStatus, utc_now
from metadata.schemas import CreateJobDTO
from utils.vstore import VECTOR_SCHEMA, get_collection_uuid

configure_logging()

logger = logging.getLogger(__name__)
settings = get_settings()


async def ensure_document(session: AsyncSession, *, tenant_id: UUID, document_id: UUID) -> Document:
    document = await session.get(Document, (tenant_id, document_id))
    if document is not None:
        return document

    document = Document(tenant_id=tenant_id, document_id=document_id)
    session.add(document)
    await session.flush()
    return document


@dataclass(frozen=True)
class _QueryClause:
    field: str | None
    value: str


_FIELD_ALIASES = {'tag': 'tags'}
_METADATA_FIELDS = {name.lower(): name for name in MetadataSchema.model_fields}


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

    await ensure_document(session, tenant_id=tenant_id, document_id=document_id)

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
    await ensure_document(session, tenant_id=tenant_id, document_id=document_id)

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


async def delete_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
) -> bool:
    document = await session.get(Document, (tenant_id, document_id))
    if document is None:
        return False

    await session.delete(document)
    await session.commit()
    return True


@asynccontextmanager
async def _vectorstore_connection(tenant_id: UUID):
    conn = await pg_connect(tenant_id)
    try:
        yield conn
    finally:
        await conn.close()


async def update_vecstore_metadata(context: ContextSchema, document_id: UUID, metadata: MetadataSchema) -> None:
    """Update cmetadata for the given document inside langchain_pg_embedding."""
    metadata_dict = metadata.model_dump(mode='json', exclude_none=True)
    metadata_dict['digest'] = context.digest
    meta_payload = json.dumps(metadata_dict)

    try:
        async with _vectorstore_connection(context.tenant_id) as conn:
            collection_uuid = await get_collection_uuid(conn, context.collection_name)
            query = f"""
                UPDATE {VECTOR_SCHEMA}.langchain_pg_embedding
                SET cmetadata = COALESCE(cmetadata, '{{}}'::jsonb) || $1::jsonb
                WHERE collection_id = $2::uuid
                  AND cmetadata ->> 'digest' = $3
            """
            await conn.execute(query, meta_payload, str(collection_uuid), context.digest)
    except Exception as e:  # noqa: BLE001 - best-effort update, log only
        logger.exception(f'Failed updating vecstore metadata for document {document_id}: {str(e)}')


def _resolve_field(field: str) -> str:
    key = field.strip().lower()
    if not key:
        raise ValueError('Filter field must not be empty')
    key = _FIELD_ALIASES.get(key, key)
    if key not in _METADATA_FIELDS:
        raise ValueError(f'Unknown metadata field: {field}')
    return _METADATA_FIELDS[key]


def _parse_search_query(query: str) -> list[_QueryClause]:
    if query is None:
        raise ValueError('Query must not be empty')
    tokens = [part.strip() for part in query.split('&') if part.strip()]
    if not tokens:
        raise ValueError('Query must not be empty')

    clauses: list[_QueryClause] = []
    for token in tokens:
        if ':' in token:
            field_part, value_part = token.split(':', 1)
            field_name = _resolve_field(field_part)
            value = value_part.strip()
            if not value:
                raise ValueError(f'Filter for "{field_part}" must include a value')
            clauses.append(_QueryClause(field=field_name, value=value.lower()))
        else:
            clauses.append(_QueryClause(field=None, value=token.lower()))
    return clauses


def _value_matches(raw_value, expected: str) -> bool:
    if raw_value is None:
        return False
    if isinstance(raw_value, list):
        values = [item for item in raw_value if item is not None]
    else:
        values = [raw_value]

    for value in values:
        text = str(value).lower()
        if expected in text:
            return True
    return False


def _matches_any_field(payload: dict, expected: str) -> bool:
    for field in _METADATA_FIELDS.values():
        if _value_matches(payload.get(field), expected):
            return True
    return False


def _payload_matches(payload: dict, clauses: list[_QueryClause]) -> bool:
    for clause in clauses:
        if clause.field is None:
            if not _matches_any_field(payload, clause.value):
                return False
        else:
            if not _value_matches(payload.get(clause.field), clause.value):
                return False
    return True


async def search_documents(session: AsyncSession, *, tenant_id: UUID, query: str) -> list[tuple[UUID, str | None]]:
    clauses = _parse_search_query(query)

    doc_meta_table = DocumentMetadata.__table__  # type: ignore[missing-attribute]
    stmt = (
        select(DocumentMetadata)
        .where(DocumentMetadata.tenant_id == tenant_id)
        .order_by(doc_meta_table.c.document_id, doc_meta_table.c.version.desc())
    )
    result = await session.exec(stmt)
    records = result.all()

    latest_by_document: dict[UUID, DocumentMetadata] = {}
    for record in records:
        if record.document_id not in latest_by_document:
            latest_by_document[record.document_id] = record

    digests_by_doc: dict[UUID, str] = {}
    if latest_by_document:
        fingerprints = {doc_id: record.fingerprint for doc_id, record in latest_by_document.items()}
        doc_ids = list(fingerprints.keys())
        job_table = Job.__table__  # type: ignore[missing-attribute]
        stmt = (
            select(job_table.c.document_id, job_table.c.processing_fingerprint, job_table.c.document_digest)
            .where(job_table.c.tenant_id == tenant_id)
            .where(job_table.c.document_id.in_(doc_ids))
            .where(job_table.c.processing_fingerprint.in_(list(fingerprints.values())))
        )
        result = await session.exec(stmt)
        for doc_id, processing_fingerprint, document_digest in result.all():
            expected = fingerprints.get(doc_id)
            if processing_fingerprint == expected:
                digests_by_doc[doc_id] = document_digest

    matches: list[tuple[UUID, str | None]] = []
    for record in latest_by_document.values():
        payload = record.payload or {}
        if _payload_matches(payload, clauses):
            digest = payload.get('digest') or digests_by_doc.get(record.document_id)
            matches.append((record.document_id, digest))

    matches.sort(key=lambda item: str(item[0]))
    return matches
