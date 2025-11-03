from __future__ import annotations

from uuid import UUID

import pytest
from starlette.datastructures import Headers, QueryParams
from tenauth.schemas import AccessContext, AuthContext
from tenauth.websocket import websocket_access_context


class DummyWebSocket:
    def __init__(self, *, headers: dict[str, str] | None = None, query: dict[str, str] | None = None) -> None:
        self.headers = Headers(headers or {})
        self.query_params = QueryParams(query or {})


@pytest.mark.asyncio()
async def test_websocket_access_context_accepts_query_token(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = AuthContext(
        sub=UUID('00000000-0000-0000-0000-000000000123'),
        tid=UUID('00000000-0000-0000-0000-000000000456'),
        role='tester',
        scopes=['*'],
    )

    monkeypatch.setattr(
        'tenauth.schemas.AuthContext.from_token',
        classmethod(lambda _cls, token: expected),
    )

    websocket = DummyWebSocket(query={'access_token': 'token-from-query'})
    access = await websocket_access_context(websocket)  # type: ignore[bad-argument-type]

    assert isinstance(access, AccessContext)
    assert access.user_id == expected.sub
    assert access.tenant_id == expected.tid


@pytest.mark.asyncio()
async def test_websocket_access_context_accepts_subprotocol_token(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = AuthContext(
        sub=UUID('00000000-0000-0000-0000-000000000AAA'),
        tid=UUID('00000000-0000-0000-0000-000000000BBB'),
        role='tester',
        scopes=['*'],
    )

    def fake_from_token(_cls: type[AuthContext], token: str) -> AuthContext:
        assert token == 'subprotocol-token'
        return expected

    monkeypatch.setattr(
        'tenauth.schemas.AuthContext.from_token',
        classmethod(fake_from_token),
    )

    websocket = DummyWebSocket(headers={'Sec-WebSocket-Protocol': 'chat, access_token=subprotocol-token'})
    access = await websocket_access_context(websocket)  # type: ignore[bad-argument-type]

    assert access.user_id == expected.sub
    assert access.tenant_id == expected.tid


@pytest.mark.asyncio()
async def test_websocket_access_context_strips_bearer_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = AuthContext(
        sub=UUID('00000000-0000-0000-0000-000000000111'),
        tid=UUID('00000000-0000-0000-0000-000000000222'),
        role='tester',
        scopes=['*'],
    )

    def fake_from_token(_cls: type[AuthContext], token: str) -> AuthContext:
        assert token == 'trimmed-token'
        return expected

    monkeypatch.setattr(
        'tenauth.schemas.AuthContext.from_token',
        classmethod(fake_from_token),
    )

    websocket = DummyWebSocket(query={'token': 'Bearer trimmed-token'})
    access = await websocket_access_context(websocket)  # type: ignore[bad-argument-type]

    assert access.user_id == expected.sub
    assert access.tenant_id == expected.tid
