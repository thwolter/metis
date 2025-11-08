from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Final, TypeVar
from uuid import UUID

import dramatiq
from sqlmodel import select

from classification.models import DocClass
from classification.service import recompute_class_prototype_batch
from core import get_settings
from core.broker import reset_broker
from core.db import pg_connection, session_factory
from core.logging import configure_logging
from metadata.models import Document

configure_logging()
reset_broker()
logger = logging.getLogger(__name__)

_EVENT_LOOP = asyncio.new_event_loop()


def _run_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


_EVENT_LOOP_THREAD = threading.Thread(target=_run_background_loop, args=(_EVENT_LOOP,), daemon=True)
_EVENT_LOOP_THREAD.start()


T = TypeVar('T')


def _run_in_event_loop(coro: Awaitable[T]) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, _EVENT_LOOP)  # type: ignore[bad-argument-type]
    return future.result()


_LABEL_KEYS: Final[tuple[str, ...]] = (
    'document_type',
    'documentType',
    'document_class',
    'doc_class',
    'docClass',
    'classification',
    'class',
)


def _label_variants(class_name: str) -> list[str]:
    normalized = class_name.strip().replace('-', '_')
    tokens = [piece for piece in normalized.split('_') if piece]
    if not tokens:
        return []

    variants = {
        normalized.lower(),
        ''.join(tokens).lower(),
        ' '.join(tokens).lower(),
        '-'.join(tokens).lower(),
    }
    return sorted(variants)


async def _list_doc_classes() -> list[str]:
    async with session_factory() as session:
        result = await session.exec(select(DocClass.class_name))
        return list(result.all())


async def _list_tenant_ids() -> list[UUID]:
    async with session_factory() as session:
        result = await session.exec(select(Document.tenant_id).distinct())
        return list(result.all())


async def _fetch_labelled_digests_for_class(
    *,
    tenant_id: UUID | None,
    class_name: str,
) -> set[str]:
    labels = _label_variants(class_name)
    if not labels:
        return set()
    settings = get_settings()
    conditions = ' OR '.join(f"lower(cmetadata->>'{key}') = ANY($1::text[])" for key in _LABEL_KEYS)
    query = f"""
        SELECT DISTINCT cmetadata->>'digest' AS digest
        FROM {settings.pg_vector_schema}.langchain_pg_embedding
        WHERE cmetadata ? 'digest'
          AND ({conditions})
    """

    digests: set[str] = set()
    try:
        async with pg_connection(tenant_id) as conn:
            await conn.execute('SET LOCAL ROLE classifier_service')
            rows = await conn.fetch(query, labels)
    except Exception:
        logger.exception('Failed fetching digests for class %s (tenant=%s)', class_name, tenant_id)
        return digests

    for row in rows:
        value = row['digest']
        if isinstance(value, str) and value:
            digests.add(value)
    return digests


@dataclass(frozen=True)
class BatchTrainerResult:
    updated: dict[str, int]
    skipped: set[str]


async def recompute_class_prototypes(
    *,
    class_names: Sequence[str] | None = None,
    tenant_ids: Sequence[UUID | None] | None = None,
) -> BatchTrainerResult:
    classes = list(dict.fromkeys(class_names or await _list_doc_classes()))
    if not classes:
        logger.info('No DocClass entries found; skipping recompute.')
        return BatchTrainerResult(updated={}, skipped=set())

    if tenant_ids is None:
        tenant_list = await _list_tenant_ids()
        tenant_set: set[UUID | None] = set(tenant_list)
        tenant_set.add(None)  # allow global / tenant-less embeddings
    else:
        tenant_set = {tenant for tenant in tenant_ids}
        if not tenant_set:
            tenant_set.add(None)
    tenants = sorted(tenant_set, key=lambda value: '' if value is None else str(value))

    updated: dict[str, int] = {}
    skipped: set[str] = set()

    async with session_factory() as session:
        for class_name in classes:
            digest_union: set[str] = set()
            for tenant_id in tenants:
                digests = await _fetch_labelled_digests_for_class(tenant_id=tenant_id, class_name=class_name)
                digest_union.update(digests)

            if not digest_union:
                skipped.add(class_name)
                logger.info('No labelled digests found for class %s; skipping prototype recompute.', class_name)
                continue

            proto = await recompute_class_prototype_batch(
                session=session,
                class_name=class_name,
                digests=sorted(digest_union),
            )
            if proto is None:
                skipped.add(class_name)
                logger.warning('Prototype recompute returned None for class %s.', class_name)
                continue
            updated[class_name] = proto.n_docs
            logger.info(
                'Recomputed prototype for %s with %d documents (dispersion %.4f).',
                class_name,
                proto.n_docs,
                proto.dispersion,
            )

    return BatchTrainerResult(updated=updated, skipped=skipped)


@dramatiq.actor
def run_prototype_batch_trainer(tenant_id: str | None = None, class_name: str | None = None) -> None:
    tenants: list[UUID | None] | None = None
    if tenant_id:
        tenants = [UUID(tenant_id)]

    classes: list[str] | None = None
    if class_name:
        classes = [class_name]

    result = _run_in_event_loop(
        recompute_class_prototypes(
            class_names=classes,
            tenant_ids=tenants,
        )
    )
    logger.info('Batch trainer completed; updated=%s skipped=%s', result.updated, sorted(result.skipped))
