from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from classification.models import ClassPrototype, DocClass
from classification.service import (
    fetch_doc_vectors_by_digests,
    recompute_class_prototype_batch,
    update_class_prototype_online,
)

# ------------------------ Fakes / Test Doubles ------------------------


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    async def execute(self, _sql: str, *_args: Any, **_kw: Any) -> None:
        # accept any SET LOCAL ROLE, etc.
        return None

    async def fetch(self, _sql: str, _digests: list[str]) -> list[dict[str, Any]]:
        # emulate filtering by digests
        want = set(_digests)
        return [r for r in self._rows if r['digest'] in want]


class _FakeConnCtx:
    """Async context manager that yields _FakeConn."""

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self._conn = _FakeConn(rows)

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeAsyncSession:
    """Minimal AsyncSession twin backed by in-memory storage."""

    def __init__(self) -> None:
        self.doc_classes: set[str] = set()
        self.prototypes: dict[str, ClassPrototype] = {}

    async def get(self, model, key):
        if model is DocClass:
            return DocClass(class_name=key, enabled=True) if key in self.doc_classes else None
        if model is ClassPrototype:
            return self.prototypes.get(key)
        return None

    def add(self, obj):
        if isinstance(obj, DocClass):
            self.doc_classes.add(obj.class_name)
        elif isinstance(obj, ClassPrototype):
            self.prototypes[obj.class_name] = obj

    async def flush(self):
        return None

    async def merge(self, proto: ClassPrototype) -> ClassPrototype:
        self.prototypes[proto.class_name] = proto
        return proto

    async def commit(self):
        return None


# ----------------------------- Fixtures ------------------------------


@pytest.fixture()
def fake_session() -> _FakeAsyncSession:
    return _FakeAsyncSession()


@pytest.fixture()
def patch_pg(monkeypatch):
    """Monkeypatch classification.service.pg_connection to return our fake connection ctx.

    Usage: set patch_pg.rows to control returned embeddings before invoking the code under test.
    """
    target_mod = __import__('classification.service', fromlist=['pg_connection'])
    state = {'rows': []}

    def _pg_connection(**_kw):  # tenant_id=None, etc.
        return _FakeConnCtx(state['rows'])  # async ctx

    monkeypatch.setattr(target_mod, 'pg_connection', _pg_connection)
    return state


# ------------------------------- Tests -------------------------------


@pytest.mark.asyncio
async def test_fetch_doc_vectors_by_digests_averages_and_normalises(patch_pg):
    # Two chunks for d1 (2D), three for d2
    patch_pg['rows'] = [
        {'digest': 'd1', 'embedding': [1.0, 0.0]},
        {'digest': 'd1', 'embedding': [0.0, 1.0]},
        {'digest': 'd2', 'embedding': [0.6, 0.8]},
        {'digest': 'd2', 'embedding': [0.6, 0.8]},
        {'digest': 'd2', 'embedding': [0.6, 0.8]},
    ]

    out = await fetch_doc_vectors_by_digests(digests=['d1', 'd2'])
    assert set(out.keys()) == {'d1', 'd2'}
    # d1 mean is (0.5, 0.5) -> unit vector at 45 degrees
    v1 = out['d1']
    assert np.allclose(np.linalg.norm(v1), 1.0, atol=1e-7)
    assert np.allclose(v1, np.array([1.0, 1.0]) / math.sqrt(2), atol=1e-6)
    # d2 already unit in expectation; average must remain unit
    v2 = out['d2']
    assert np.allclose(np.linalg.norm(v2), 1.0, atol=1e-7)
    assert np.allclose(v2, np.array([0.6, 0.8]), atol=1e-6)


@pytest.mark.asyncio
async def test_recompute_class_prototype_creates_class_and_proto(fake_session, patch_pg):
    # Single digest with two orthogonal chunks -> centroid along (1,1)
    patch_pg['rows'] = [
        {'digest': 'd1', 'embedding': [1.0, 0.0]},
        {'digest': 'd1', 'embedding': [0.0, 1.0]},
    ]

    proto = await recompute_class_prototype_batch(session=fake_session, class_name='annual_report', digests=['d1'])
    assert proto is not None
    # class was created
    assert 'annual_report' in fake_session.doc_classes
    # prototype persisted
    stored = fake_session.prototypes.get('annual_report')
    assert stored is not None
    assert stored.n_docs == 1  # one document digest
    assert 0.0 <= stored.dispersion <= 1.0
    # centroid should be unit and close to (1,1)/sqrt(2)
    mu = np.asarray(stored.centroid, dtype=float)
    assert np.allclose(np.linalg.norm(mu), 1.0, atol=1e-7)
    assert np.allclose(mu, np.array([1.0, 1.0]) / math.sqrt(2), atol=1e-6)


@pytest.mark.asyncio
async def test_update_class_prototype_online_inserts_then_updates(fake_session, patch_pg):
    # First digest near e1
    patch_pg['rows'] = [
        {'digest': 'a', 'embedding': [1.0, 0.0, 0.0]},
        {'digest': 'a', 'embedding': [0.9, 0.1, 0.0]},
    ]

    proto1 = await update_class_prototype_online(
        session=fake_session, class_name='company_register', digest='a', ema_alpha=0.1
    )
    assert proto1 is not None
    assert proto1.n_docs == 1
    mu1 = np.asarray(proto1.centroid, dtype=float)
    assert np.allclose(np.linalg.norm(mu1), 1.0, atol=1e-7)

    # Second digest near e1 as well -> n_docs=2 and centroid stays close to e1
    patch_pg['rows'] = [
        {'digest': 'b', 'embedding': [1.0, 0.0, 0.0]},
        {'digest': 'b', 'embedding': [0.95, 0.05, 0.0]},
    ]

    proto2 = await update_class_prototype_online(
        session=fake_session, class_name='company_register', digest='b', ema_alpha=0.1
    )
    assert proto2 is not None
    assert proto2.n_docs == 2
    mu2 = np.asarray(proto2.centroid, dtype=float)
    assert np.allclose(np.linalg.norm(mu2), 1.0, atol=1e-7)
    # direction mostly along first axis
    assert mu2[0] > 0.9
