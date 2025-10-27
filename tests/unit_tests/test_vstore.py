from __future__ import annotations

from uuid import UUID

import pytest

from utils.vstore import get_collection_uuid


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
