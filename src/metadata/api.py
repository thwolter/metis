from __future__ import annotations

import asyncio
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session
from tenauth.fastapi import require_auth

from agent.schemas import MetadataSchema
from core.db import get_session, session_scope
from metadata import tasks
from metadata.models import Job, JobStatus
from metadata.schemas import (
    CreateJobDTO,
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
    fetch_document_metadata,
    get_job,
    manual_metadata_update,
)

router = APIRouter(
    prefix='/v1',
    tags=['metadata'],
    dependencies=[Depends(require_auth)],
)

TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}


def _status_url(request: Request, job_id: UUID) -> str:
    return str(request.url_for('get_job_status', job_id=str(job_id)))


def _result_url(request: Request, document_id: UUID, version: str = 'latest') -> str:
    url = request.url_for('get_document_metadata', document_id=str(document_id))
    return f'{url}?version={version}'


async def _wait_for_completion(job_id: UUID, wait_for_secs: int) -> Job | None:
    if wait_for_secs <= 0:
        return None

    deadline = time.monotonic() + wait_for_secs
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job and job.status in TERMINAL_STATUSES:
                return job
    return None


@router.post(
    '/metadata',
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_metadata_job(
    payload: CreateJobDTO,
    request: Request,
    session: Session = Depends(get_session),
    wait_for_secs: int = Query(default=0, ge=0, le=30),
):
    job = create_job(session, payload)
    tasks.enqueue_job(job.job_id)

    response = JobCreatedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status_url=_status_url(request, job.job_id),
    )

    awaited_job = await _wait_for_completion(job.job_id, wait_for_secs)
    if awaited_job and awaited_job.status == JobStatus.SUCCEEDED:
        response.result_url = _result_url(request, awaited_job.document_id)
    return response


@router.post(
    '/documents/{document_id}/rebuild',
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_document_metadata(
    document_id: UUID,
    payload: RebuildJobDTO,
    request: Request,
    session: Session = Depends(get_session),
):
    job_payload = payload.model_copy(update={'document_id': document_id})
    job = create_job(session, job_payload)
    tasks.enqueue_job(job.job_id)
    return JobCreatedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status_url=_status_url(request, job.job_id),
    )


@router.get('/jobs/{job_id}', response_model=JobStatusResponse, name='get_job_status')
def get_job_status(job_id: UUID, request: Request, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
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


@router.delete('/jobs/{job_id}', response_model=JobCancelResponse, status_code=status.HTTP_202_ACCEPTED)
def cancel_job_handler(job_id: UUID, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Job not found')
    job = cancel_job(session, job)
    return JobCancelResponse(job_id=job.job_id, status=job.status)


@router.get(
    '/documents/{document_id}/metadata',
    response_model=MetadataVersionResponse,
    name='get_document_metadata',
)
def get_document_metadata(
    document_id: UUID,
    request: Request,
    version: VersionQuery = Query(default='latest'),
    session: Session = Depends(get_session),
):
    record = fetch_document_metadata(session, document_id=document_id, version=version)
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
)
def upsert_document_metadata(
    document_id: UUID,
    payload: ManualMetadataUpdateDTO,
    session: Session = Depends(get_session),
):
    record = manual_metadata_update(session, document_id=document_id, metadata=payload.metadata)
    metadata = MetadataSchema.model_validate(record.payload)
    return MetadataVersionResponse(
        document_id=record.document_id,
        version=record.version,
        fingerprint=record.fingerprint,
        extracted_on=record.extracted_on,
        metadata=metadata,
    )
