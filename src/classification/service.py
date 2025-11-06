from __future__ import annotations

from typing import Any, Iterable, Sequence
from uuid import UUID

import numpy as np
from sqlmodel.ext.asyncio.session import AsyncSession

from core.db import pg_connection
from metadata.service import ensure_document
from utils.vstore import VECTOR_SCHEMA

from .models import ClassificationRun, ClassPrototype, DocClass
from .utils import l2, normalise_vector


def _topk_mean(v: np.ndarray, k: int) -> float:
    # helper if you later decide to use robust pooling; unused in centroid
    k = max(1, min(k, v.shape[0]))
    return float(np.mean(np.sort(v)[-k:]))


async def fetch_doc_vectors_by_digests(
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
    dry_run: bool = False,
) -> ClassPrototype | None:
    """
    Accurate batch refresh: build centroid/dispersion from the provided labelled digests.
    Persists ClassPrototype (JSON centroid) via the async Session.
    """
    doc_vecs = await fetch_doc_vectors_by_digests(
        digests=digests,
    )
    if not doc_vecs:
        return None

    mu, disp, n_docs = _centroid_and_dispersion(doc_vecs.values())

    if dry_run:
        # Return a computed, in-memory prototype; no persistence, no side effects.
        return ClassPrototype(
            class_name=class_name,
            centroid=mu.tolist(),
            dispersion=disp,
            n_docs=n_docs,
        )

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


def _compute_updated_proto(
    *,
    class_name: str,
    existing: ClassPrototype | None,
    dvec: np.ndarray,
    ema_alpha: float,
) -> ClassPrototype:
    """
    Pure function: given an optional existing prototype and a new document vector,
    return the updated prototype (UNMANAGED). No DB side-effects.
    """
    if existing is None:
        # First observation for this class
        return ClassPrototype(
            class_name=class_name,
            centroid=dvec.tolist(),
            dispersion=0.0,
            n_docs=1,
        )

    # Running-mean style update (normalise at the end)
    sum_vec = np.asarray(existing.centroid, dtype=float) * max(existing.n_docs, 1)
    sum_vec = sum_vec + dvec
    mu = l2(sum_vec.reshape(1, -1))[0]
    sim = float(dvec @ mu)
    disp = (1.0 - ema_alpha) * existing.dispersion + ema_alpha * (1.0 - sim)

    return ClassPrototype(
        class_name=class_name,
        centroid=mu.tolist(),
        dispersion=disp,
        n_docs=existing.n_docs + 1,
    )


async def update_class_prototype_online(
    *,
    session: AsyncSession,
    class_name: str,
    digest: str,
    ema_alpha: float = 0.1,
    dry_run: bool = False,
) -> ClassPrototype | None:
    """
    Fast online update from a single newly-labelled digest.

    - dry_run=True: compute and return the would-be prototype (no DB writes).
    - dry_run=False: persist the change (ensure class exists, upsert prototype).
    """
    doc_vecs = await fetch_doc_vectors_by_digests(digests=[digest])
    if not doc_vecs:
        return None

    dvec = next(iter(doc_vecs.values()))

    # Lookup only (safe for dry_run)
    existing_cls = await session.get(DocClass, class_name)
    existing_proto = await session.get(ClassPrototype, class_name)

    # Compute the target prototype (pure, shared path)
    target = _compute_updated_proto(
        class_name=class_name,
        existing=existing_proto,
        dvec=dvec,
        ema_alpha=ema_alpha,
    )

    if dry_run:
        return target  # no side-effects

    # Persisted path
    if existing_cls is None:
        session.add(DocClass(class_name=class_name, enabled=True))
        await session.flush()

    if existing_proto is None:
        session.add(target)
        await session.commit()
        return target

    # Apply deltas to the managed instance
    existing_proto.centroid = target.centroid
    existing_proto.dispersion = target.dispersion
    existing_proto.n_docs = target.n_docs
    session.add(existing_proto)
    await session.commit()
    return existing_proto


async def persist_classification_run(
    session: AsyncSession,
    *,
    document_id: UUID,
    config: dict[str, Any],
    prob: float,
    margin: float,
    chunks_used: int,
    predicted_class: str | None,
) -> ClassificationRun:
    """Insert a classification run row (fire-and-forget semantics)."""
    # todo: We can remove tenant_id after using tenant_id_field in metdata.Documents
    tenant_id = session.info['tenant_id']
    await ensure_document(session, tenant_id=tenant_id, document_id=document_id)
    run = ClassificationRun(
        document_id=document_id,
        predicted_class=predicted_class,
        prob=prob,
        margin=margin,
        chunks_used=chunks_used,
        config=config,  # JSON
    )
    session.add(run)
    await session.commit()
    # If you need the row back with server defaults, uncomment:
    # await session.refresh(run)
    return run
