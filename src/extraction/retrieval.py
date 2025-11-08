from __future__ import annotations

import math
from typing import Iterable, Sequence
from uuid import UUID

from langchain_core.documents import Document
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from classification.models import HeaderWeight
from utils.vstore import get_vectorstore

from .schemas import AttributeSpec, RetrievalConfig, RetrievedChunk

HEADER_KEYS = ('header', 'Header 1', 'Header 2', 'Header 3', 'Header 4')


async def _load_header_weights(session: AsyncSession, doc_type: str) -> list[tuple[str, bool, float]]:
    """
    Load header weighting hints for the target doc_type from the classification schema.
    """
    stmt = select(
        HeaderWeight.pattern,
        HeaderWeight.is_regex,
        HeaderWeight.weight,
    ).where(HeaderWeight.class_name == doc_type)
    result = await session.exec(stmt)
    return [(pattern, bool(is_regex), float(weight)) for pattern, is_regex, weight in result.all()]


def _compose_header(metadata: dict[str, object]) -> str | None:
    values: list[str] = []
    for key in HEADER_KEYS:
        raw = metadata.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
    if not values:
        return None
    return ' > '.join(values)


def _text_excerpt(text: str, limit: int = 320) -> str:
    snippet = text.strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1].rstrip() + '…'


def _header_bonus(header: str | None, weights: Sequence[tuple[str, bool, float]], scale: float) -> float:
    if not header or not weights:
        return 0.0
    header_lower = header.lower()
    bonus = 0.0
    for pattern, is_regex, weight in weights:
        try:
            if is_regex:
                import re

                if re.search(pattern, header, flags=re.IGNORECASE):
                    bonus += weight
            else:
                if pattern.lower() in header_lower:
                    bonus += weight
        except Exception:
            continue
    return bonus * scale


def _hint_bonus(text: str, hints: Iterable[str], weight: float) -> float:
    if weight <= 0:
        return 0.0
    text_lower = text.lower()
    score = 0.0
    for hint in hints:
        if hint and hint.lower() in text_lower:
            score += weight
    return score


async def _build_search_query(attribute: AttributeSpec) -> str:
    hints = list(attribute.hints)
    queries = [' '.join(part for part in (attribute.name.replace('_', ' '), attribute.description) if part)]
    if hints:
        queries.append(' '.join(hints))
    if attribute.regex_hint:
        queries.append(attribute.regex_hint)
    query = ' '.join(q for q in queries if q)
    return query


async def retrieve_chunks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    collection_name: str,
    digest: str,
    doc_type: str,
    attribute: AttributeSpec,
    config: RetrievalConfig,
) -> list[RetrievedChunk]:
    """
    Hybrid retrieval for the attribute-centric extraction pipeline.
    """
    vs = get_vectorstore(collection_name=collection_name, tenant_id=tenant_id)
    query = await _build_search_query(attribute)

    results: list[tuple[Document, float]] = await vs.asimilarity_search_with_score(
        query,
        k=config.max_chunks * 2,
        filter={'$and': [{'digest': {'$eq': digest}}]},
    )
    header_weights = await _load_header_weights(session, doc_type)

    scored: list[tuple[float, Document]] = []
    for doc, base_score in results:
        metadata = doc.metadata or {}
        header = _compose_header(metadata)
        base_score = float(base_score)
        # PGVector returns distance; convert to similarity if negative.
        if base_score < 0:
            base_score = 1 / (1 + math.exp(base_score))

        bonus = 0.0
        bonus += _header_bonus(header, header_weights, config.header_boost)
        bonus += _hint_bonus(doc.page_content, attribute.hints, config.hints_weight)
        scored.append((base_score * config.semantic_weight + bonus, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_docs = scored[: config.max_chunks]
    chunks: list[RetrievedChunk] = []
    for score, doc in top_docs:
        metadata = doc.metadata or {}
        chunk_id = metadata.get('chunk_id') or metadata.get('chunkId') or metadata.get('id')
        chunk_id_str = str(chunk_id) if chunk_id is not None else ''
        page = metadata.get('page') or metadata.get('page_number')
        page_val = int(page) if isinstance(page, (int, float)) else None
        header = _compose_header(metadata)
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id_str,
                text=doc.page_content,
                header=header,
                page=page_val,
                retr_score=score,
            )
        )
    return chunks
