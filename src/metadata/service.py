from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable
from uuid import UUID

from sqlalchemy import desc, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent.schemas import MetadataSchema
from metadata.models import Document, DocumentMetadata

_FIELD_ALIASES = {'tag': 'tags'}
_METADATA_FIELDS = {name.lower(): name for name in MetadataSchema.model_fields.keys()}


async def ensure_document(session: AsyncSession, *, tenant_id: UUID, document_id: UUID) -> Document:
    """
    Ensure a metadata.Document row exists for the given tenant/document pair.
    """
    document: Document | None = await session.get(Document, (tenant_id, document_id))
    if document is not None:
        return document
    document = Document(tenant_id=tenant_id, document_id=document_id)
    session.add(document)
    await session.commit()
    return document


def _fingerprint_from_payload(payload: dict) -> str:
    normalised = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return sha256(normalised.encode('utf-8')).hexdigest()


def metadata_fingerprint(metadata: MetadataSchema) -> str:
    payload = metadata.model_dump(mode='json', by_alias=True, exclude_none=False)
    return _fingerprint_from_payload(payload)


async def next_metadata_version(session: AsyncSession, tenant_id: UUID, document_id: UUID) -> int:
    stmt = select(func.max(DocumentMetadata.version)).where(
        DocumentMetadata.tenant_id == tenant_id,
        DocumentMetadata.document_id == document_id,
    )
    result = await session.exec(stmt)
    current = result.one_or_none()
    return (current or 0) + 1


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
        payload: dict = {}
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
    """
    Persist a manual metadata version, skipping automated extraction.
    """
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


@dataclass(frozen=True, slots=True)
class _QueryClause:
    field: str | None
    value: str


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
        values: Iterable = [item for item in raw_value if item is not None]
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

    metadata_table = DocumentMetadata.__table__  # type: ignore[missing-attribute]

    stmt = (
        select(DocumentMetadata)
        .where(
            DocumentMetadata.tenant_id == tenant_id,
        )
        .order_by(metadata_table.c.document_id, metadata_table.c.version.desc())
    )
    result = await session.exec(stmt)
    records = result.all()

    latest_by_document: dict[UUID, DocumentMetadata] = {}
    for record in records:
        if record.document_id not in latest_by_document:
            latest_by_document[record.document_id] = record

    matches: list[tuple[UUID, str | None]] = []
    for record in latest_by_document.values():
        payload = record.payload or {}
        if _payload_matches(payload, clauses):
            digest = payload.get('digest')
            matches.append((record.document_id, digest))

    matches.sort(key=lambda item: str(item[0]))
    return matches
