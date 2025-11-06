from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from classification.inference import InferenceResult, predict_document_class
from classification.service import (
    fetch_doc_vectors_by_digests,
    persist_classification_run,
    recompute_class_prototype_batch,
    update_class_prototype_online,
)
from core.deps import SessionDep

from .schemas import (
    OnlineUpdateRequest,
    OnlineUpdateResponse,
    PredictByChunks,
    PredictByDigest,
    PredictRequest,
    PredictResponse,
    RecomputeRequest,
    RecomputeResponse,
)

router = APIRouter(prefix='/api/classification', tags=['classification'])


@router.post('/recompute', response_model=RecomputeResponse)
async def recompute_endpoint(
    payload: RecomputeRequest,
    session: AsyncSession = Depends(SessionDep),
):
    proto = await recompute_class_prototype_batch(
        session=session, class_name=payload.class_name, digests=payload.digests, dry_run=payload.dry_run
    )
    if proto is None:
        raise HTTPException(status_code=404, detail='No vectors for digests')
    return RecomputeResponse(
        class_name=payload.class_name,
        centroid_dim=len(proto.centroid),
        n_docs=proto.n_docs,
        dispersion=proto.dispersion,
        updated=not payload.dry_run,
        dry_run=payload.dry_run,
    )


@router.post('/online-update', response_model=OnlineUpdateResponse)
async def online_update_endpoint(
    payload: OnlineUpdateRequest,
    session: AsyncSession = Depends(SessionDep),
):
    proto = await update_class_prototype_online(
        session=session,
        class_name=payload.class_name,
        digest=payload.digest,
        ema_alpha=payload.ema_alpha,
        dry_run=payload.dry_run,
    )
    if proto is None:
        raise HTTPException(status_code=404, detail='Digest not found')
    return OnlineUpdateResponse(
        class_name=payload.class_name,
        centroid_dim=len(proto.centroid),
        n_docs=proto.n_docs,
        dispersion=proto.dispersion,
        updated=not payload.dry_run,
        dry_run=payload.dry_run,
    )


async def check_threshold(
    *, payload: PredictByDigest | PredictByChunks, inference: InferenceResult
) -> tuple[bool, str | None]:
    """Apply simple global thresholds (no legacy, no per-class overrides).

    Thresholds model:
        class Thresholds(BaseModel):
            min_prob: float | None
            min_margin: float | None
            min_chunks: int | None
    """
    thresholds = getattr(payload, 'thresholds', None)
    if thresholds is None:
        return False, None

    # Extract with safe defaults
    min_prob = getattr(thresholds, 'min_prob', None)
    min_margin = getattr(thresholds, 'min_margin', None)
    min_chunks = getattr(thresholds, 'min_chunks', None)

    # Apply checks in order: prob -> margin -> chunks
    if min_prob is not None and inference.prob < min_prob:
        return True, 'below_min_prob'
    if min_margin is not None and inference.margin < min_margin:
        return True, 'below_min_margin'
    if min_chunks is not None and inference.chunks_used < min_chunks:
        return True, 'below_min_chunks'

    return False, None


@router.post('/predict', response_model=PredictResponse)
async def predict_endpoint(
    payload: PredictRequest,
    session: AsyncSession = Depends(SessionDep),
):
    chunk_embeddings = None
    chunk_headers = None
    if getattr(payload, 'mode', None) == 'by_chunks':
        chunk_embeddings = [np.asarray(v, dtype=float) for v in getattr(payload, 'chunk_embeddings', [])]
        chunk_headers = getattr(payload, 'chunk_headers', None)
        # Check chunk_headers length if provided
        if chunk_headers is not None and len(chunk_headers) != len(chunk_embeddings):
            raise HTTPException(status_code=400, detail='chunk_headers length mismatch')

    try:
        res = await predict_document_class(
            session=session,
            mode=payload.mode,  # "by_digest" | "by_chunks"
            digests=(getattr(payload, 'digests', None) or None),
            chunk_embeddings=chunk_embeddings,
            chunk_headers=chunk_headers,
            fetch_doc_vectors=fetch_doc_vectors_by_digests,
            m_chunk=payload.m_chunk,
            header_weight_scale=payload.header_weight_scale,
            # thresholds removed from here
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    abstained, reason = await check_threshold(payload=payload, inference=res)

    # Persist every prediction attempt
    config = {
        'mode': payload.mode,
        'm_chunk': payload.m_chunk,
        'header_weight_scale': payload.header_weight_scale,
        # Provide lightweight provenance only; avoid heavy blobs
        'input': {
            'digests': getattr(payload, 'digests', None) if payload.mode == 'by_digest' else None,
            'n_chunks': len(getattr(payload, 'chunk_embeddings', [])) if payload.mode == 'by_chunks' else None,
            'has_headers': bool(getattr(payload, 'chunk_headers', None)) if payload.mode == 'by_chunks' else False,
        },
        'thresholds': (
            payload.thresholds.model_dump()
            if hasattr(payload.thresholds, 'model_dump')
            else (
                payload.thresholds.dict()
                if hasattr(payload.thresholds, 'dict')
                else (payload.thresholds if isinstance(payload.thresholds, dict) else None)
            )
        ),
        'abstained': abstained,
        'reason': reason,
    }
    await persist_classification_run(
        session=session,
        document_id=payload.document_id,
        config=config,
        prob=res.prob,
        margin=res.margin,
        chunks_used=res.chunks_used,
        predicted_class=(None if abstained else res.predicted_class),
    )

    return PredictResponse(
        predicted_class=None if abstained else res.predicted_class,
        prob=res.prob,
        margin=res.margin,
        chunks_used=res.chunks_used,
        scores=res.scores,
        abstained=abstained,
        reason=reason,
    )
