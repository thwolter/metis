from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocketState
from tenauth.fastapi import require_access_context
from tenauth.schemas import AccessContext
from tenauth.session import access_scoped_session_ctx
from tenauth.websocket import websocket_access_context

from core.config import get_settings
from core.db import scoped_session, session_factory
from core.deps import SessionDep
from extraction.events import broker
from extraction.graph import _resolve_execution_config, run_extraction
from extraction.models import ExtractedAttribute, ExtractionJob, ExtractionJobStatus
from extraction.persistence import (
    create_extraction_job,
    increment_sequence,
    update_job_status,
)
from extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatusPayload,
    StatusEvent,
)

router = APIRouter(
    prefix='/v1/extraction',
    tags=['Extraction'],
)

stream_router = APIRouter(prefix='/v1')

TERMINAL_EXTRACTION_EVENTS = {
    StatusEvent.JOB_COMPLETED.value,
    StatusEvent.JOB_FAILED.value,
    StatusEvent.JOB_CANCELED.value,
}

TERMINAL_STATUSES = {
    ExtractionJobStatus.COMPLETED,
    ExtractionJobStatus.FAILED,
    ExtractionJobStatus.CANCELED,
}


class ExtractionRunPayload(ExtractionRequest):
    class Config:
        json_schema_extra = {
            'example': {
                'doc_id': '11111111-2222-3333-4444-555555555555',
                'doc_type': 'annual_report',
                'digest': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
                'collection_name': 'annual-reports',
                'attributes': ['company_name', 'isin'],
                'model': 'openai:gpt-4o-mini',
                'retriever': {'max_chunks': 8, 'top_m': 4, 'header_boost': 0.8},
                'dry_run': False,
            }
        }


class ExtractionJobResponse(ExtractionResult):
    status_url: str
    stream_url: str


class ExtractionJobStatusResponse(BaseModel):
    job_id: UUID
    doc_id: UUID
    doc_type: str
    status: ExtractionJobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    seq: int
    results: dict[str, Any] | None = None


class ExtractionJobCancelResponse(BaseModel):
    job_id: UUID
    status: ExtractionJobStatus


async def _load_results(session: AsyncSession, job_id: UUID) -> dict[str, Any]:
    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == job_id)
    rows = (await session.exec(stmt)).all()
    results: dict[str, Any] = {}
    for record in rows:
        payload = record.value_json or {}
        results[record.attribute] = {
            'value': payload.get('value'),
            'confidence': record.confidence,
            'provenance': record.provenance,
            'rationale': payload.get('rationale'),
        }
    return results


def _aware(dt_value: datetime | None) -> datetime:
    stamp = dt_value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def _terminal_event(status: ExtractionJobStatus) -> StatusEvent:
    if status == ExtractionJobStatus.COMPLETED:
        return StatusEvent.JOB_COMPLETED
    if status == ExtractionJobStatus.CANCELED:
        return StatusEvent.JOB_CANCELED
    return StatusEvent.JOB_FAILED


async def _terminal_extraction_payload(session: AsyncSession, job: ExtractionJob) -> dict[str, Any]:
    results = await _load_results(session, job.job_id)
    payload = ExtractionStatusPayload(
        seq=job.seq,
        timestamp=_aware(job.finished_at or job.updated_at),
        job_id=job.job_id,
        doc_id=job.doc_id,
        doc_type=job.doc_type,
        event=_terminal_event(job.status),
        status=job.status.value,
        progress=None,
        attribute=None,
        provenance=None,
        summary=None,
        errors=[job.error] if job.error else None,
        attributes=None,
        results=results,
    )
    return payload.model_dump(mode='json')


async def _execute_job(
    job_id: UUID,
    request_payload: dict[str, Any],
    access: AccessContext,
) -> None:
    req = ExtractionRequest.model_validate(request_payload)
    async with scoped_session(access_context=access) as session:
        job = await session.get(ExtractionJob, job_id)
        if job is None:
            return
        if job.status == ExtractionJobStatus.CANCELED:
            await session.commit()
            return

        update_data: dict[str, Any] = {}
        if req.digest is None:
            update_data['digest'] = job.document_digest
        if req.collection_name is None:
            update_data['collection_name'] = job.collection_name
        if update_data:
            req = req.model_copy(update=update_data)

        async def _emit_callback(jid: UUID, payload: dict[str, Any]) -> None:
            await broker.publish(jid, payload)

        try:
            await run_extraction(
                session,
                req,
                emit=_emit_callback,
                job=job,
            )
        except Exception:
            # run_extraction handles status updates; make sure failure does not crash background task
            pass
        finally:
            await session.commit()


@router.post(
    '/run',
    response_model=ExtractionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_extraction_endpoint(
    payload: ExtractionRunPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> ExtractionJobResponse:
    extraction_request = ExtractionRequest.model_validate(payload.model_dump())
    extraction_request = extraction_request.model_copy(update={'tenant_id': access.tenant_id})

    if not extraction_request.digest or not extraction_request.collection_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='digest and collection_name must be provided',
        )

    settings = get_settings()
    retrieval_config, model_name, model_version = _resolve_execution_config(settings, extraction_request)

    job = await create_extraction_job(
        session,
        tenant_id=access.tenant_id,
        doc_id=extraction_request.doc_id,
        doc_type=extraction_request.doc_type,
        model=model_name,
        model_version=model_version,
        retriever_config=retrieval_config.model_dump(mode='json'),
        options={'dry_run': extraction_request.dry_run},
        document_digest=extraction_request.digest,
        collection_name=extraction_request.collection_name,
    )
    await session.commit()

    background_tasks.add_task(
        _execute_job,
        job.job_id,
        extraction_request.model_dump(mode='json'),
        access,
    )

    status_url = str(request.url_for('get_extraction_job_status', job_id=str(job.job_id)))
    stream_url = str(request.url_for('stream_job_status', job_id=str(job.job_id)))

    return ExtractionJobResponse(
        job_id=job.job_id,
        doc_id=extraction_request.doc_id,
        doc_type=extraction_request.doc_type,
        attributes={},
        model=model_name,
        model_version=model_version,
        started_at=job.created_at,
        completed_at=None,
        errors=[],
        status_url=status_url,
        stream_url=stream_url,
    )


@router.get(
    '/jobs/{job_id}',
    response_model=ExtractionJobStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_extraction_job_status(
    job_id: UUID,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> ExtractionJobStatusResponse:
    job = await session.get(ExtractionJob, job_id)
    if job is None or job.tenant_id != access.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Job not found')

    results = None
    if job.status == ExtractionJobStatus.COMPLETED:
        results = await _load_results(session, job.job_id)

    return ExtractionJobStatusResponse(
        job_id=job.job_id,
        doc_id=job.doc_id,
        doc_type=job.doc_type,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        seq=job.seq,
        results=results,
    )


@router.post(
    '/jobs/{job_id}/cancel',
    response_model=ExtractionJobCancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_extraction_job(
    job_id: UUID,
    session: AsyncSession = Depends(SessionDep),
    access: AccessContext = Depends(require_access_context),
) -> ExtractionJobCancelResponse:
    job = await session.get(ExtractionJob, job_id)
    if job is None or job.tenant_id != access.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Job not found')

    if job.status in TERMINAL_STATUSES:
        return ExtractionJobCancelResponse(job_id=job.job_id, status=job.status)

    job = await update_job_status(
        session,
        job,
        status=ExtractionJobStatus.CANCELED,
        error='canceled by user',
    )
    await increment_sequence(session, job)

    payload = await _terminal_extraction_payload(session, job)
    await session.commit()
    await broker.publish(job.job_id, payload)

    return ExtractionJobCancelResponse(job_id=job.job_id, status=job.status)


@stream_router.websocket('/jobs/{job_id}/stream', name='stream_job_status')
async def stream_job_status(websocket: WebSocket, job_id: UUID):
    access = await websocket_access_context(websocket)
    async with access_scoped_session_ctx(
        session_factory=session_factory,
        access_context=access,
    ) as session:
        job = await session.get(ExtractionJob, job_id)
        if job is None or job.tenant_id != access.tenant_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='Job not found')

        await websocket.accept()

        if job.status in TERMINAL_STATUSES and job.seq == 0:
            payload = await _terminal_extraction_payload(session, job)
            await websocket.send_json(payload)
            if websocket.application_state is WebSocketState.CONNECTED:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
            return

        try:
            if job.status in TERMINAL_STATUSES:
                payload = await _terminal_extraction_payload(session, job)
                await websocket.send_json(payload)
                if websocket.application_state is WebSocketState.CONNECTED:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                return

            async for message in broker.subscribe(job.job_id):
                await websocket.send_json(message)
                if message.get('event') in TERMINAL_EXTRACTION_EVENTS:
                    break
        except WebSocketDisconnect:
            return
        finally:
            if websocket.application_state is WebSocketState.CONNECTED:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)


__all__ = ['router', 'stream_router']
