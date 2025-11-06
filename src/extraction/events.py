from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator
from uuid import UUID


class ExtractionEventBroker:
    """In-memory pub-sub for extraction job status events."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, job_id: UUID, payload: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(job_id, []))
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop oldest event and ensure we push the latest per spec
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(payload)

    async def subscribe(self, job_id: UUID, max_buffer: int = 100) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_buffer)
        async with self._lock:
            self._subscribers[job_id].add(queue)
        try:
            while True:
                payload = await queue.get()
                yield payload
        finally:
            async with self._lock:
                self._subscribers[job_id].discard(queue)
                if not self._subscribers[job_id]:
                    self._subscribers.pop(job_id, None)


broker = ExtractionEventBroker()
