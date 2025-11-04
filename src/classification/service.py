from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import pg_connection
from utils.vstore import VECTOR_SCHEMA

from .models import ClassPrototype, DocClass
from .utils import l2, normalise_vector


def _topk_mean(v: np.ndarray, k: int) -> float:
    # helper if you later decide to use robust pooling; unused in centroid
    k = max(1, min(k, v.shape[0]))
    return float(np.mean(np.sort(v)[-k:]))


async def _fetch_doc_vectors_by_digests(
    *,
    digests: Sequence[str],
) -> dict[str, np.ndarray]:
    """
    Build one unit vector per document digest by averaging its chunk embeddings (then L2-normalising).
    Reads directly from PGVector, matching your tools.py access pattern.
    """
    if not digests:
        return {}

    doc_rows: dict[str, list[np.ndarray]] = {}

    async with pg_connection(tenant_id=None) as conn:
        await conn.execute('SET LOCAL ROLE classifier_service')
        rows = await conn.fetch(
            f"""
            SELECT (cmetadata->>'digest') AS digest, embedding
            FROM {VECTOR_SCHEMA}.langchain_pg_embedding
            WHERE (cmetadata->>'digest') = ANY ($1::text[])
            """,
            list(digests),
        )

    for row in rows:
        dg = row['digest']
        val = row['embedding']
        # Normalize to a numpy float array
        emb = await normalise_vector(val)
        emb = l2(emb.reshape(1, -1))[0]
        doc_rows.setdefault(dg, []).append(emb)

    # average per digest, then normalise again to a unit doc vector
    doc_vecs: dict[str, np.ndarray] = {}
    for dg, chunks in doc_rows.items():
        M = np.vstack(chunks)
        dv = l2(np.mean(M, axis=0, keepdims=True))[0]
        doc_vecs[dg] = dv
    return doc_vecs


def _centroid_and_dispersion(doc_vecs: Iterable[np.ndarray]) -> tuple[np.ndarray, float, int]:
    """Mean unit centroid and average (1 - cos) dispersion over doc vectors."""
    V = np.vstack(list(doc_vecs))  # (n, d)
    mu = l2(np.mean(V, axis=0, keepdims=True))[0]
    sims = V @ mu  # cosine on unit vectors = dot
    disp = float(np.mean(1.0 - sims))
    return mu, disp, V.shape[0]


async def recompute_class_prototype_batch(
    *,
    session: AsyncSession,
    class_name: str,
    digests: Sequence[str],
) -> ClassPrototype | None:
    """
    Accurate batch refresh: build centroid/dispersion from the provided labelled digests.
    Persists ClassPrototype (JSON centroid) via the async Session.
    """
    doc_vecs = await _fetch_doc_vectors_by_digests(
        digests=digests,
    )
    if not doc_vecs:
        return None

    mu, disp, n_docs = _centroid_and_dispersion(doc_vecs.values())

    # ensure class exists and upsert prototype (async path only)
    existing_cls = await session.get(DocClass, class_name)
    if existing_cls is None:
        session.add(DocClass(class_name=class_name, enabled=True))
        await session.flush()

    proto = ClassPrototype(
        class_name=class_name,
        centroid=mu.tolist(),
        dispersion=disp,
        n_docs=n_docs,
    )
    managed = await session.merge(proto)
    await session.commit()
    return managed


async def update_class_prototype_online(
    *,
    session: AsyncSession,
    class_name: str,
    digest: str,
    ema_alpha: float = 0.1,
) -> None | ClassPrototype | type[ClassPrototype]:
    """
    Fast online update from a single newly-labelled digest.
    Uses running-sum approximation if you haven't added a persistent sum_vec column.
    """
    doc_vecs = await _fetch_doc_vectors_by_digests(
        digests=[digest],
    )
    if not doc_vecs:
        return None

    dvec = next(iter(doc_vecs.values()))

    # ensure class exists (async)
    existing_cls = await session.get(DocClass, class_name)
    if existing_cls is None:
        session.add(DocClass(class_name=class_name, enabled=True))
        await session.flush()

    proto = await session.get(ClassPrototype, class_name)
    if proto is None:
        proto = ClassPrototype(
            class_name=class_name,
            centroid=dvec.tolist(),
            dispersion=0.0,
            n_docs=1,
        )
        session.add(proto)
        await session.commit()
        return proto

    # running mean approximation
    sum_vec = np.asarray(proto.centroid, dtype=float) * max(proto.n_docs, 1)
    sum_vec = sum_vec + dvec
    mu = l2(sum_vec.reshape(1, -1))[0]
    sim = float(dvec @ mu)
    disp = (1.0 - ema_alpha) * proto.dispersion + ema_alpha * (1.0 - sim)

    proto.centroid = mu.tolist()
    proto.dispersion = disp
    proto.n_docs = proto.n_docs + 1
    session.add(proto)
    await session.commit()
    return proto
