from __future__ import annotations

from datasifter.interfaces import ProgressSink
from datasifter.schemas import ExtractionStatusPayload

from extraction.events import ExtractionEventBroker


class BrokerProgressSink(ProgressSink):
    def __init__(self, broker: ExtractionEventBroker):
        self._broker = broker

    async def publish(self, payload: ExtractionStatusPayload) -> None:
        await self._broker.publish(payload.job_id, payload.model_dump(mode='json'))


__all__ = ['BrokerProgressSink']
