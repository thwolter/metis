from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from tenauth.schemas import AccessContext
from tenauth.session import access_scoped_session_ctx

from core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.async_postgres_url.get_secret_value()
        _engine = create_async_engine(url, echo=settings.debug or False, pool_pre_ping=True, pool_recycle=3600)
    return _engine


@asynccontextmanager
async def session_factory() -> AsyncIterator[AsyncSession]:
    global _sessionmaker

    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(bind=get_engine(), class_=AsyncSession, expire_on_commit=False)

    session = _sessionmaker()
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
