from __future__ import annotations

from datasifter import ExtractionRequest, JobState, JobStatus, RetrievalConfig

from .models import ExtractionJob


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


def job_state_from_model(model: ExtractionJob, *, base: JobState | None = None) -> JobState:
    payload = {
        'job_id': model.job_id,
        'doc_id': model.doc_id,
        'doc_type': model.doc_type,
        'model': model.model,
        'model_version': model.model_version,
        'status': JobStatus(getattr(model.status, 'value', model.status)),
        'tenant_id': model.tenant_id,
        'document_digest': model.document_digest,
        'collection_name': model.collection_name,
        'started_at': model.started_at,
        'finished_at': model.finished_at,
        'error': model.error,
        'retriever_config': model.retriever_config,
        'options': model.options,
        'seq': model.seq,
    }
    if base is None:
        state = JobState(**payload)
    else:
        for key, value in payload.items():
            setattr(base, key, value)
        state = base
    state.context.setdefault('orm', model)
    state.context['orm'] = model
    return state
