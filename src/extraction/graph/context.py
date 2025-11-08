from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from extraction.graph.progress import AttributeState, ProgressTracker
from extraction.graph.status import BrokerCallback, StatusEmitter
from extraction.map_step import MapExtractor
from extraction.models import ExtractionJob, ExtractionJobStatus
from extraction.schemas import ExtractionRequest, RetrievalConfig


class ExtractionCancelledError(Exception):
    """Raised when an extraction job is canceled."""


@dataclass
class ExtractionContext:
    session: AsyncSession
    request: ExtractionRequest
    job: ExtractionJob
    retrieval_config: RetrievalConfig
    collection_name: str
    digest: str
    map_extractor: MapExtractor
    emitter: StatusEmitter
    progress: ProgressTracker
    attribute_states: dict[str, AttributeState]

    async def ensure_active(self) -> None:
        await self.session.refresh(self.job)
        if self.job.status == ExtractionJobStatus.CANCELED:
            raise ExtractionCancelledError()


def build_extraction_context(
    *,
    session: AsyncSession,
    request: ExtractionRequest,
    job: ExtractionJob,
    retrieval_config: RetrievalConfig,
    digest: str,
    collection_name: str,
    model_name: str,
    emit: BrokerCallback | None,
    progress: ProgressTracker,
    attribute_states: dict[str, AttributeState],
) -> ExtractionContext:
    emitter = StatusEmitter(
        session,
        job=job,
        doc_id=request.doc_id,
        doc_type=request.doc_type,
        callback=emit,
        progress=progress,
        attribute_states=attribute_states,
    )

    return ExtractionContext(
        session=session,
        request=request,
        job=job,
        retrieval_config=retrieval_config,
        collection_name=collection_name,
        digest=digest,
        map_extractor=MapExtractor(model=model_name),
        emitter=emitter,
        progress=progress,
        attribute_states=attribute_states,
    )


__all__ = ['ExtractionCancelledError', 'ExtractionContext', 'build_extraction_context']
