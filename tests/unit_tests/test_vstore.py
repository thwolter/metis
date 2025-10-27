from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr

from utils import vstore
from utils.vstore import get_collection_uuid, get_vectorstore


class DummyConnection:
    last_query: str | None
    last_args: tuple[object, ...] | None

    def __init__(self, row):
        self._row = row
        self.last_query = None
        self.last_args = None

    async def fetchrow(self, query, *args):
        self.last_query = query
        self.last_args = args
        return self._row


@pytest.mark.asyncio
async def test_get_collection_uuid_returns_string():
    row = {'uuid': UUID('66fe9540-a7ba-4ac8-8fdf-00a6cb5680c9')}
    conn = DummyConnection(row)

    value = await get_collection_uuid(conn, 'test-collection')  # type: ignore[bad-argument-type]

    assert value == '66fe9540-a7ba-4ac8-8fdf-00a6cb5680c9'
    assert conn.last_query is not None
    assert 'langchain_pg_collection' in conn.last_query
    assert conn.last_args == ('test-collection',)


@pytest.mark.asyncio
async def test_get_collection_uuid_missing_collection():
    conn = DummyConnection(None)

    with pytest.raises(ValueError, match='test-collection'):
        await get_collection_uuid(conn, 'test-collection')  # type: ignore[bad-argument-type]


@pytest.mark.asyncio
async def test_get_collection_uuid_empty_value():
    conn = DummyConnection({'uuid': '   '})

    with pytest.raises(ValueError, match='empty UUID'):
        await get_collection_uuid(conn, 'test-collection')  # type: ignore[bad-argument-type]


def test_get_vectorstore_uses_async_driver(monkeypatch):
    captured = {}

    class DummyEmbeddings:
        pass

    def fake_pgvector(**kwargs):
        captured.update(kwargs)
        return 'pg'

    def fake_dsn_with_tenant(dsn: str, tenant_id: UUID) -> str:
        return f'{dsn}?options=-c%20app.tenant_id%3D{tenant_id}'

    secret = SecretStr('postgresql+asyncpg://user:pass@localhost/db')
    monkeypatch.setattr(
        vstore,
        'settings',
        SimpleNamespace(async_postgres_url=secret, pg_vector_schema='vectra'),
    )
    monkeypatch.setattr(vstore, 'VECTOR_SCHEMA', 'vectra')
    monkeypatch.setattr('utils.vstore.OpenAIEmbeddings', lambda model: DummyEmbeddings())
    monkeypatch.setattr('utils.vstore.PGVector', fake_pgvector)
    monkeypatch.setattr('utils.vstore.dsn_with_tenant', fake_dsn_with_tenant)

    tenant_id = UUID('4d2ab7eb-f4f1-4114-9f5f-07e8c9eaca21')
    result = get_vectorstore(collection_name='foo', tenant_id=tenant_id)

    assert result == 'pg'
    assert captured['connection'].startswith('postgresql+asyncpg://')
    assert 'app.tenant_id' in captured['connection']
