from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from extraction.graph.progress import AttributeState, ProgressTracker
from extraction.models import ExtractionJob, ExtractionJobStatus
from extraction.persistence import increment_sequence
from extraction.schemas import ExtractionStatusPayload, StatusEvent

BrokerCallback = Callable[[UUID, dict[str, Any]], Awaitable[None]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StatusEmitter:
    def __init__(
        self,
        session: AsyncSession,
        *,
        job: ExtractionJob,
        doc_id: UUID,
        doc_type: str,
        callback: BrokerCallback | None,
        progress: ProgressTracker,
        attribute_states: dict[str, AttributeState],
    ):
        self._session = session
        self._job = job
        self._doc_id = doc_id
        self._doc_type = doc_type
        self._callback = callback
        self._progress = progress
        self._attribute_states = attribute_states
        self._lock = asyncio.Lock()

    async def emit(
        self,
        event: StatusEvent,
        *,
        status_override: ExtractionJobStatus | None = None,
        attribute_payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        summary: str | None = None,
        errors: list[str] | None = None,
        include_snapshot: bool = False,
        results: dict[str, Any] | None = None,
    ) -> ExtractionStatusPayload:
        async with self._lock:
            seq = await increment_sequence(self._session, self._job)
            status_text: ExtractionJobStatus = status_override or self._job.status
            payload = ExtractionStatusPayload(
                seq=seq,
                timestamp=_utcnow(),
                job_id=self._job.job_id,
                doc_id=self._doc_id,
                doc_type=self._doc_type,
                event=event,
                status=status_text,
                progress=self._progress.snapshot() if include_snapshot else None,
                attribute=attribute_payload,
                provenance=provenance,
                summary=summary,
                errors=errors,
                attributes=[state.to_progress() for state in self._attribute_states.values()]
                if include_snapshot
                else None,
                results=results,
            )
            if self._callback is not None:
                await self._callback(self._job.job_id, payload.model_dump(mode='json'))
            return payload


__all__ = ['BrokerCallback', 'StatusEmitter']
