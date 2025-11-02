from __future__ import annotations

import asyncio
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.fastapi import require_access_context
from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from core.deps import SessionDep
from metadata import tasks
from metadata.models import Job, JobStatus
from metadata.schemas import (
    CreateJobDTO,
    DocumentSearchResponse,
    JobCancelResponse,
    JobCreatedResponse,
    JobStatusResponse,
    ManualMetadataUpdateDTO,
    MetadataVersionResponse,
    RebuildJobDTO,
    VersionQuery,
)
from metadata.service import (
    cancel_job,
    create_job,
    delete_document,
    fetch_document_metadata,
    get_job,
    manual_metadata_update,
    search_documents,
)

router = APIRouter(
    prefix='/v1',
)

TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}


def _status_url(request: Request, job_id: UUID) -> str:
    return str(request.url_for('get_job_status', job_id=str(job_id)))


def _result_url(request: Request, document_id: UUID, version: str = 'latest') -> str:
    url = request.url_for('get_document_metadata', document_id=str(document_id))
    return f'{url}?version={version}'


async def _wait_for_completion(session: AsyncSession, *, job_id: UUID, wait_for_secs: int) -> Job | None:
    if wait_for_secs <= 0:
        return None

    deadline = time.monotonic() + wait_for_secs
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        job = await get_job(session, job_id)
        if job and job.status in TERMINAL_STATUSES:
            return job
    return None


@router.post('/metadata', response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED, tags=['Jobs'])
async def create_metadata_job(
    payload: CreateJobDTO,
    request: Request,
    session: AsyncSession = Depends(SessionDep),
    wait_for_secs: int = Query(default=0, ge=0, le=30),
    access: AccessContext = Depends(require_access_context),
):
    job = await create_job(session, payload, access_context=access)
    tasks.enqueue_job(job.job_id, job.tenant_id, job.user_id)

    response = JobCreatedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status_url=_status_url(request, job.job_id),
    )

    awaited_job = await _wait_for_completion(session, job_id=job.job_id, wait_for_secs=wait_for_secs)
    if awaited_job and awaited_job.status == JobStatus.SUCCEEDED:
        response.result_url = _result_url(request, awaited_job.document_id)
    return response


@router.post(
    '/documents/{document_id}/rebuild',
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=['Jobs'],
)
async def rebuild_document_metadata(
    document_id: UUID,
    payload: RebuildJobDTO,
    request: Request,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
):
    job_payload = payload.model_copy(update={'document_id': document_id})
    job = await create_job(session, job_payload, access_context=access)
    tasks.enqueue_job(job.job_id, job.tenant_id, job.user_id)
    return JobCreatedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status_url=_status_url(request, job.job_id),
    )


@router.get('/jobs/{job_id}', response_model=JobStatusResponse, name='get_job_status', tags=['Jobs'])
async def get_job_status(job_id: UUID, request: Request, session: AsyncSession = Depends(SessionDep)):
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Job not found')

    result_url = None
    if job.status == JobStatus.SUCCEEDED:
        result_url = _result_url(request, job.document_id)

    return JobStatusResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        tenant_id=job.tenant_id,
        status=job.status,
        retries=job.retries,
        priority=job.priority,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_type=job.error_type,
        error_msg=job.error_msg,
        result_url=result_url,
    )


@router.delete(
    '/jobs/{job_id}',
    response_model=JobCancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=['Jobs'],
)
async def cancel_job_handler(job_id: UUID, session: AsyncSession = Depends(SessionDep)):
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Job not found')
    job = await cancel_job(session, job)
    return JobCancelResponse(job_id=job.job_id, status=job.status)


@router.get(
    '/documents/{document_id}/metadata',
    response_model=MetadataVersionResponse,
    name='get_document_metadata',
    tags=['Documents'],
)
async def get_document_metadata(
    document_id: UUID,
    request: Request,
    version: VersionQuery = Query(default='latest'),
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
):
    record = await fetch_document_metadata(
        session, tenant_id=access.tenant_id, document_id=document_id, version=version
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
):
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
):
    deleted = await delete_document(session, tenant_id=access.tenant_id, document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Document not found')


@router.get('/documents/search', response_model=DocumentSearchResponse, tags=['Documents'])
async def search_document_metadata(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
):
    try:
        matches = await search_documents(session, tenant_id=access.tenant_id, query=q)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    document_ids = [document_id for document_id, _ in matches]
    digests = [digest for _, digest in matches]
    return DocumentSearchResponse(document_ids=document_ids, digests=digests)
