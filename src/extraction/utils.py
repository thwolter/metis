from __future__ import annotations

from .schemas import ExtractionRequest, RetrievalConfig


def resolve_execution_config(
    settings,
    request: ExtractionRequest,
) -> RetrievalConfig:
    """Resolves the configuration for the retrieval task based on the provided settings and extraction request."""
    if request.retriever is None:
        return RetrievalConfig(
            max_chunks=settings.extraction.max_chunks,
            top_m=settings.extraction.top_m,
            header_boost=settings.extraction.header_boost,
            semantic_weight=1.0,
            bm25_weight=0.5,
            hints_weight=0.3,
        )
    return request.retriever
