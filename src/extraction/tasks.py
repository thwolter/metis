from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import dramatiq
from dramatiq.brokers.stub import StubBroker
from tenauth.schemas import AccessContext

from core.broker import broker as dramatiq_broker
from core.db import scoped_session

from .events import broker as event_broker
from .graph import run_extraction
from .models import ExtractionJob, ExtractionJobStatus
from .schemas import ExtractionRequest

logger = logging.getLogger(__name__)


async def _execute_job(job_id: UUID, request_payload: dict[str, Any], access_payload: dict[str, Any]) -> None:
    """Run an extraction job using the shared async pipeline."""
    access = AccessContext.model_validate(access_payload)
    req = ExtractionRequest.model_validate(request_payload)

    async with scoped_session(access_context=access) as session:
        job = await session.get(ExtractionJob, job_id)
        if job is None:
            logger.warning('Extraction job %s missing; dropping task.', job_id)
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
            await event_broker.publish(jid, payload)

        try:
            await run_extraction(
                session,
                req,
                emit=_emit_callback,
                job=job,
            )
        except Exception:
            logger.exception('Extraction job %s failed during execution.', job_id)
        finally:
            await session.commit()


@dramatiq.actor
def run_extraction_job(job_id: str, request_payload: dict[str, Any], access_payload: dict[str, Any]) -> None:
    """Dramatiq entrypoint executed by worker processes."""
    asyncio.run(_execute_job(UUID(job_id), request_payload, access_payload))


def queue_extraction_job(*, job_id: UUID, request: ExtractionRequest, access: AccessContext) -> None:
    """Send the extraction job to Dramatiq or fall back to in-process execution."""
    message_args = (
        str(job_id),
        request.model_dump(mode='json'),
        access.model_dump(mode='json'),
    )

    if isinstance(dramatiq_broker, StubBroker):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_execute_job(UUID(message_args[0]), message_args[1], message_args[2]))
        else:
            loop.create_task(_execute_job(UUID(message_args[0]), message_args[1], message_args[2]))
        return

    run_extraction_job.send(*message_args)


__all__ = ['queue_extraction_job', 'run_extraction_job']
