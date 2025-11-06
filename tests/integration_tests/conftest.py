from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import AsyncGenerator
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.engine import make_url
from tenauth.fastapi import require_access_context, require_auth
from tenauth.schemas import AccessContext, AuthContext
from tenauth.websocket import websocket_access_context
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from core import db as core_db
from core.config import get_settings
from core.db import scoped_session, session_factory
from main import app as main_app
from tests.db import (  # type: ignore[missing-import]
    prepare_database,
    reset_database_state,
    run_migrations,
)

DEFAULT_ENV_VARS = {
    'JWT_SECRET': 'test-secret',
    'ENV': 'testing',
    'DOCUMENT_STORE': 'local',
    'OPENAI_API_KEY': 'test-key',
    'TAVILY_API_KEY': 'test-key',
}

for key, value in DEFAULT_ENV_VARS.items():
    os.environ.setdefault(key, value)

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AuthenticatedTestClient:
    """Wrapper merging async HTTP support with synchronous WebSocket helpers."""

    def __init__(self, async_client: AsyncClient, websocket_client: TestClient) -> None:
        self._async_client = async_client
        self._websocket_client = websocket_client

    def websocket_connect(self, *args, **kwargs):
        return self._websocket_client.websocket_connect(*args, **kwargs)

    def __getattr__(self, item: str):
        return getattr(self._async_client, item)


@pytest.fixture(scope='session', autouse=True)
async def integration_environment() -> AsyncGenerator[None, None]:
    """Spin up Postgres (pgvector) and Redis via Testcontainers for integration tests.

    - Prepares two DSNs: app and alembic
    - Runs Alembic migrations once
    - Resets DB state and seeds
    - Ensures core.db engine is reinitialized
    """

    postgres = PostgresContainer('pgvector/pgvector:pg16')
    redis = RedisContainer('redis:6-alpine')

    postgres.start()
    redis.start()

    try:
        base_url = make_url(postgres.get_connection_url(driver='asyncpg'))
        app_dsn, alembic_dsn = await prepare_database(base_url)
        redis_url = f'redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0'

        os.environ['POSTGRES_URL'] = app_dsn.render_as_string(hide_password=False)
        os.environ['ALEMBIC_DATABASE_URL'] = alembic_dsn.render_as_string(hide_password=False)
        os.environ['REDIS_URL'] = redis_url

        for key, value in DEFAULT_ENV_VARS.items():
            os.environ.setdefault(key, value)

        get_settings.cache_clear()

        if core_db._engine is not None:
            await core_db._engine.dispose()
        core_db._engine = None
        # Reset sessionmaker to avoid cross-event-loop reuse
        if getattr(core_db, '_sessionmaker', None) is not None:
            core_db._sessionmaker = None

        run_migrations()
        await reset_database_state()
        yield
    finally:
        with suppress(Exception):
            redis.stop()
        with suppress(Exception):
            postgres.stop()


@pytest.fixture(autouse=True)
async def _clean_db_between_tests():
    """Ensure a clean DB before and after each test in integration suite."""
    await reset_database_state()
    yield
    await reset_database_state()


tenant_id = UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde')
user_id = UUID('11111111-1111-1111-1111-111111111111')


@pytest.fixture
async def any_session():
    """Provide a DB session for the default test user/tenant."""
    async with session_factory() as s:
        yield s


@pytest.fixture
async def auth_session():
    """Provide a DB session for the default test user/tenant."""
    ctx = AccessContext(
        tenant_id=tenant_id,
        user_id=user_id,
    )
    async with scoped_session(access_context=ctx) as s:
        yield s


@pytest.fixture
async def session_another_user():
    """Same tenant, different user."""
    # Create a new session with a different user but same tenant
    ctx = AccessContext(
        tenant_id=tenant_id,
        user_id=UUID('00000000-0000-0000-0000-000000000001'),
    )
    async with scoped_session(access_context=ctx) as s:
        yield s


@pytest.fixture
async def session_another_tenant():
    """Different tenant and user."""
    ctx = AccessContext(
        tenant_id=UUID('00000000-0000-0000-0000-000000000001'),
        user_id=UUID('00000000-0000-0000-0000-000000000000'),
    )
    async with scoped_session(access_context=ctx) as s:
        yield s


@pytest.fixture(scope='session', autouse=True)
def override_auth_dependencies():
    from main import app

    async def _fake_get_current_auth():
        return AuthContext(sub=user_id, tid=tenant_id, role='tester', scopes=['*'])

    async def _fake_get_access_context():
        return AccessContext(tenant_id=tenant_id, user_id=user_id)

    app.dependency_overrides[require_auth] = _fake_get_current_auth
    app.dependency_overrides[require_access_context] = _fake_get_access_context

    async def _fake_websocket_access_context(*_: object, **__: object) -> AccessContext:
        return AccessContext(tenant_id=tenant_id, user_id=user_id)

    app.dependency_overrides[websocket_access_context] = _fake_websocket_access_context
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
async def auth_client() -> AsyncGenerator[AsyncClient]:
    """Async HTTP client bound to the FastAPI app under test.

    Ensures app startup/shutdown via the app's lifespan context for compatibility
    with httpx versions where ASGITransport does not accept a `lifespan` kwarg.
    This keeps everything in a single event loop and avoids cross-loop issues.
    """
    async with main_app.router.lifespan_context(main_app):
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client


@pytest.fixture(scope='session')
def sync_client() -> TestClient:
    """Synchronous TestClient for WebSocket and in-process tests."""
    return TestClient(main_app)
