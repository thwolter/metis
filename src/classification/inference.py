from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

import numpy as np
from numpy.typing import NDArray
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import ClassPrototype, DocClass, HeaderWeight
from .utils import as_float_vec1d, filter_prototypes_by_dim, l2, softmax


@dataclass(frozen=True)
class InferenceResult:
    predicted_class: str | None
    prob: float
    margin: float
    chunks_used: int
    scores: Mapping[str, float]


EmbeddingArray = NDArray[np.floating[Any]]
EmbeddingSeq = Sequence[EmbeddingArray]
EmbeddingInput = EmbeddingSeq | EmbeddingArray
PrototypeMap = Mapping[str, EmbeddingArray]


class DocVectorFetcher(Protocol):
    async def __call__(self, *, digests: Sequence[str]) -> dict[str, np.ndarray]: ...


async def _load_enabled_prototypes(session: AsyncSession) -> dict[str, np.ndarray]:
    """Load enabled classes and their centroids as unit vectors."""
    rows = (
        await session.exec(
            select(ClassPrototype.class_name, ClassPrototype.centroid)
            .join(ClassPrototype.doc_class)
            .where(DocClass.enabled.is_(True))  # type: ignore[missing-attribute]
        )
    ).all()
    protos: dict[str, np.ndarray] = {}
    for cls, centroid in rows:
        v = as_float_vec1d(centroid)
        protos[cls] = l2(v.reshape(1, -1))[0]
    return protos


async def _load_header_weights(session: AsyncSession) -> dict[str, list[tuple[str, bool, float]]]:
    rows = (
        await session.exec(
            select(
                HeaderWeight.class_name,
                HeaderWeight.pattern,
                HeaderWeight.is_regex,
                HeaderWeight.weight,
            )
        )
    ).all()
    out: dict[str, list[tuple[str, bool, float]]] = {}
    for cls, pattern, is_rx, w in rows:
        out.setdefault(cls, []).append((pattern, bool(is_rx), float(w)))
    return out


def _header_bonus_per_chunk(
    header: str | None,
    per_class_patterns: dict[str, list[tuple[str, bool, float]]],
    weight_scale: float,
) -> dict[str, float]:
    if not header:
        return {cls: 0.0 for cls in per_class_patterns.keys()}
    bonuses: dict[str, float] = {}
    for cls, patterns in per_class_patterns.items():
        b = 0.0
        for pat, is_rx, w in patterns:
            try:
                if is_rx:
                    import re

                    if re.search(pat, header, flags=re.IGNORECASE):
                        b += w
                else:
                    if pat.lower() in header.lower():
                        b += w
            except Exception:
                # Never fail inference due to a bad pattern
                continue
        bonuses[cls] = b * weight_scale
    return bonuses


def _informative_chunks(base_scores: EmbeddingArray, m_chunk: int, n: int) -> Any:
    """Select top-m informative chunks based on best-vs-second gap per chunk."""
    if base_scores.shape[1] >= 2:
        part = np.partition(base_scores, -2, axis=1)
        gap = part[:, -1] - part[:, -2]
    else:
        gap = base_scores[:, 0]
    order = np.argsort(-gap)  # descending
    m = max(1, min(m_chunk, n))
    top_idx = order[:m].tolist()
    return top_idx


def _add_header_bonus(
    c_names: list[str],
    base_scores: EmbeddingArray,
    chunk_headers: Sequence[str | None] | None,
    header_weights: dict[str, list[tuple[str, bool, float]]],
    weight_scale: float,
):
    # Header bonus per chunk per class
    if chunk_headers is not None and header_weights:
        for i, h in enumerate(chunk_headers):
            bonuses = _header_bonus_per_chunk(h, header_weights, weight_scale)
            for j, cls in enumerate(c_names):
                base_scores[i, j] += bonuses.get(cls, 0.0)


def _normalise_chunk_embeddings(chunk_embeddings: EmbeddingInput) -> list[EmbeddingArray]:
    """
    Ensure chunk embeddings are a list of 1-D float arrays, regardless of whether the
    caller supplied a sequence of vectors or a stacked ndarray.
    """
    if isinstance(chunk_embeddings, np.ndarray):
        arr = np.asarray(chunk_embeddings, dtype=float)
        if arr.ndim == 1:
            return [arr.reshape(-1)]
        if arr.ndim == 2:
            return [arr[i, :].reshape(-1) for i in range(arr.shape[0])]
        raise ValueError('Chunk embeddings must be a 1-D vector or 2-D matrix.')
    items: list[EmbeddingArray] = []
    for emb in chunk_embeddings:
        arr = np.asarray(emb, dtype=float)
        if arr.ndim != 1:
            arr = arr.reshape(-1)
        items.append(arr)
    return items


def _to_embedding_array(chunk_embeddings: EmbeddingSeq) -> tuple[EmbeddingArray, int]:
    """Stack chunk embeddings into a 2D array and return the dimensionality."""

    first = chunk_embeddings[0]
    d = first.size
    chunks_1d = [first]
    for e in chunk_embeddings[1:]:
        if e.size != d:
            raise ValueError(f'Chunk embedding dimension mismatch: expected {d}, got {e.size}')
        chunks_1d.append(e)
    X = np.vstack([l2(v.reshape(1, -1))[0] for v in chunks_1d])  # [n,d]
    return X, d


def _calculate_cosine_scores(chunk_embeddings: EmbeddingSeq, protos: PrototypeMap) -> tuple[list[str], EmbeddingArray]:
    """Calculate cosine class scores for each chunk."""

    X, d = _to_embedding_array(chunk_embeddings)
    C_cols, c_names = filter_prototypes_by_dim(dim=d, protos=protos)
    if not C_cols:
        raise ValueError(f'No class prototypes match chunk dimension d={d}')
    else:
        C = np.vstack(C_cols).T  # [d,k]
    base_scores = X @ C  # [n,k]
    return c_names, base_scores


def _select_informative_chunks(
    chunk_embeddings: EmbeddingSeq,
    chunk_headers: Sequence[str | None] | None,
    protos: Mapping[str, np.ndarray],
    header_weights: dict[str, list[tuple[str, bool, float]]],
    m_chunk: int,
    weight_scale: float,
) -> tuple[list[int], np.ndarray, list[str]]:
    """
    Rank chunks by max(class score) where score = cos(emb, proto) + header_bonus.
    Return indices of top-m, the precomputed score matrix [n_chunks, n_classes], and class names.
    """
    n = len(chunk_embeddings)
    if n == 0:
        return [], np.zeros((0, len(protos)), dtype=float), []

    c_names, base_scores = _calculate_cosine_scores(chunk_embeddings, protos)
    _add_header_bonus(c_names, base_scores, chunk_headers, header_weights, weight_scale)

    top_idx = _informative_chunks(base_scores, m_chunk, n)
    return top_idx, base_scores, c_names


async def predict_document_class(
    *,
    session: AsyncSession,
    mode: Literal['by_chunks', 'by_digest'] = 'by_chunks',
    chunk_embeddings: EmbeddingInput | None = None,
    chunk_headers: Sequence[str | None] | None = None,
    digests: Sequence[str] | None = None,
    fetch_doc_vectors: DocVectorFetcher | None = None,
    m_chunk: int = 8,
    k_doc: int = 5,  # reserved if you later ensemble multiple centroids per class
    header_weight_scale: float = 0.05,
) -> InferenceResult:
    """
    Predict class using KNN against class centroids with informative-chunk selection and
    optional header-weight bonuses.
    """
    # Resolve inputs based on mode
    if mode == 'by_digest':
        if not digests:
            return InferenceResult(predicted_class=None, prob=0.0, margin=0.0, chunks_used=0, scores={})
        if fetch_doc_vectors is None:
            raise ValueError("fetch_doc_vectors callback must be provided for mode='by_digest'.")
        doc_vecs = await fetch_doc_vectors(digests=digests)
        if not doc_vecs:
            return InferenceResult(predicted_class=None, prob=0.0, margin=0.0, chunks_used=0, scores={})
        _embeddings: EmbeddingInput = list(doc_vecs.values())
        _headers: Sequence[str | None] | None = None
    elif mode == 'by_chunks':
        if chunk_embeddings is None:
            return InferenceResult(predicted_class=None, prob=0.0, margin=0.0, chunks_used=0, scores={})
        _embeddings = chunk_embeddings
        _headers = chunk_headers
    else:
        raise ValueError(f'Unknown mode: {mode}')

    chunk_list = _normalise_chunk_embeddings(_embeddings)

    protos = await _load_enabled_prototypes(session)
    if not protos:
        return InferenceResult(predicted_class=None, prob=0.0, margin=0.0, chunks_used=0, scores={})

    header_weights = await _load_header_weights(session)

    # Pick informative chunks and aggregate class scores over them
    idx, score_matrix, c_names = _select_informative_chunks(
        chunk_embeddings=chunk_list,
        chunk_headers=_headers,
        protos=protos,
        header_weights=header_weights,
        m_chunk=m_chunk,
        weight_scale=header_weight_scale,
    )
    if not idx:
        return InferenceResult(predicted_class=None, prob=0.0, margin=0.0, chunks_used=0, scores={})

    sel = score_matrix[idx, :]  # [m,k]
    agg = sel.mean(axis=0)  # average across informative chunks

    # Decision statistics
    sm = softmax(agg)
    top = int(np.argmax(agg))
    sorted_idx = np.argsort(-agg)
    margin = float(agg[sorted_idx[0]] - agg[sorted_idx[1]]) if agg.size >= 2 else float(agg[sorted_idx[0]])

    scores_map = {c_names[i]: float(agg[i]) for i in range(len(c_names))}
    return InferenceResult(
        predicted_class=c_names[top],
        prob=float(sm[top]),
        margin=margin,
        chunks_used=len(idx),
        scores=scores_map,
    )
