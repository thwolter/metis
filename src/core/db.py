from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID
from weakref import WeakKeyDictionary

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.schemas import AccessContext
from tenauth.session import access_scoped_session_ctx

from core.config import get_settings

Loop = asyncio.AbstractEventLoop
SessionFactory = async_sessionmaker[AsyncSession]

_engine_cache: WeakKeyDictionary[Loop, AsyncEngine] = WeakKeyDictionary()
_sessionmaker_cache: WeakKeyDictionary[Loop, SessionFactory] = WeakKeyDictionary()


def _current_loop() -> Loop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError('A running event loop is required to access the async engine') from exc


def get_engine() -> AsyncEngine:
    loop = _current_loop()
    engine = _engine_cache.get(loop)
    if engine is None:
        settings = get_settings()
        url = settings.async_postgres_url.get_secret_value()
        engine = create_async_engine(url, echo=settings.debug or False, pool_pre_ping=True, pool_recycle=3600)
        _engine_cache[loop] = engine
    return engine


def _get_sessionmaker() -> SessionFactory:
    loop = _current_loop()
    sessionmaker = _sessionmaker_cache.get(loop)
    if sessionmaker is None:
        sessionmaker = async_sessionmaker(bind=get_engine(), class_=AsyncSession, expire_on_commit=False)
        _sessionmaker_cache[loop] = sessionmaker
    return sessionmaker


@asynccontextmanager
async def session_factory() -> AsyncIterator[AsyncSession]:
    session = _get_sessionmaker()()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def scoped_session(*, access_context: AccessContext, verify: bool = True) -> AsyncIterator[AsyncSession]:
    async with access_scoped_session_ctx(
        session_factory=session_factory,
        access_context=access_context,
        verify=verify,
    ) as session:
        exc: Exception | None = None
        try:
            yield session
        except Exception as err:
            exc = err
            raise
        finally:
            if exc is None:
                await session.commit()


async def pg_connect(tenant_id: UUID | None) -> asyncpg.Connection:
    settings = get_settings()
    dsn_secret = settings.postgres_url
    if dsn_secret is None:
        msg = 'postgres_url must be configured before opening a direct connection'
        raise RuntimeError(msg)
    dsn = dsn_secret.get_secret_value()
    dsn = dsn.replace('+asyncpg://', '://', 1)
    if tenant_id is None:
        return await asyncpg.connect(dsn=dsn)
    return await asyncpg.connect(dsn=dsn, server_settings={'app.tenant_id': str(tenant_id)})


@asynccontextmanager
async def pg_connection(tenant_id: UUID | None) -> AsyncIterator[asyncpg.Connection]:
    conn = await pg_connect(tenant_id)
    try:
        yield conn
    finally:
        await conn.close()


async def dispose_engines() -> None:
    """Dispose every cached engine and clear per-loop session factories."""
    engines = list(_engine_cache.values())
    _engine_cache.clear()
    _sessionmaker_cache.clear()
    for engine in engines:
        await engine.dispose()
