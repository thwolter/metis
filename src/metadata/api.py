from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.fastapi import require_access_context
from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from core.deps import SessionDep
from metadata.schemas import (
    DocumentSearchResponse,
    ManualMetadataUpdateDTO,
    MetadataVersionResponse,
    VersionQuery,
)
from metadata.service import (
    delete_document,
    fetch_document_metadata,
    manual_metadata_update,
    search_documents,
)

router = APIRouter(prefix='/v1', tags=['Documents'])


@router.get(
    '/documents/{document_id}/metadata',
    response_model=MetadataVersionResponse,
    name='get_document_metadata',
    tags=['Documents'],
)
async def get_document_metadata(
    document_id: UUID,
    version: VersionQuery = Query(default='latest'),
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> MetadataVersionResponse:
    record = await fetch_document_metadata(
        session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        version=version,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Metadata not found')

    metadata = MetadataSchema.model_validate(record.payload)
    return MetadataVersionResponse(
        document_id=record.document_id,
        version=record.version,
        fingerprint=record.fingerprint,
        extracted_on=record.extracted_on,
        metadata=metadata,
    )


@router.put(
    '/documents/{document_id}/metadata',
    response_model=MetadataVersionResponse,
    tags=['Documents'],
)
async def upsert_document_metadata(
    document_id: UUID,
    payload: ManualMetadataUpdateDTO,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> MetadataVersionResponse:
    record = await manual_metadata_update(
        session,
        document_id=document_id,
        metadata=payload.metadata,
        tenant_id=access.tenant_id,
    )
    metadata = MetadataSchema.model_validate(record.payload)
    return MetadataVersionResponse(
        document_id=record.document_id,
        version=record.version,
        fingerprint=record.fingerprint,
        extracted_on=record.extracted_on,
        metadata=metadata,
    )


@router.delete(
    '/documents/{document_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    tags=['Documents'],
)
async def delete_document_handler(
    document_id: UUID,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> None:
    deleted = await delete_document(session, tenant_id=access.tenant_id, document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Document not found')


@router.get('/documents/search', response_model=DocumentSearchResponse, tags=['Documents'])
async def search_document_metadata(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> DocumentSearchResponse:
    try:
        matches = await search_documents(session, tenant_id=access.tenant_id, query=q)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    document_ids = [document_id for document_id, _ in matches]
    digests = [digest for _, digest in matches]
    return DocumentSearchResponse(document_ids=document_ids, digests=digests)
