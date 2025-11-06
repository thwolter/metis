from __future__ import annotations

from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from classification.inference import predict_document_class
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


@router.post('/predict', response_model=PredictResponse)
async def predict_endpoint(
    payload: PredictRequest,
    session: AsyncSession = Depends(SessionDep),
):
    chunk_embeddings = None
    if getattr(payload, 'mode', None) == 'by_chunks':
        chunk_embeddings = [np.asarray(v, dtype=float) for v in getattr(payload, 'chunk_embeddings', [])]
    chunk_headers = None
    if getattr(payload, 'mode', None) == 'by_chunks':
        chunk_headers = getattr(payload, 'chunk_headers', None)

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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    abstained = False
    reason: Optional[str] = None
    if getattr(payload, 'thresholds', None):
        th = payload.thresholds  # type: ignore[attr-defined]
        if th:
            if res.prob < th.min_prob:
                abstained, reason = True, 'below_min_prob'
            if res.margin < th.min_margin:
                abstained, reason = True, 'below_min_margin' if not reason else reason

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
        'abstained': abstained,
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
