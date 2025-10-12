from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine
from tenauth.schemas import AccessContext

from core.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.pg_vector_url.get_secret_value()
        _engine = create_engine(url, echo=settings.debug or False, pool_pre_ping=True, pool_recycle=3600)
    return _engine


def _apply_access_context(session: Session, access_context: AccessContext) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name.startswith('postgresql'):
        session.execute(
            text("SELECT set_config('app.tenant_id', :value, false)"),
            {'value': str(access_context.tenant_id)},
        )
        session.execute(
            text("SELECT set_config('app.user_id', :value, false)"),
            {'value': str(access_context.user_id)},
        )

    session.info['tenant_id'] = access_context.tenant_id
    session.info['user_id'] = access_context.user_id


def _reset_access_context(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name.startswith('postgresql'):
        session.execute(text('RESET app.user_id'))
        session.execute(text('RESET app.tenant_id'))

    session.info.pop('tenant_id', None)
    session.info.pop('user_id', None)


@contextmanager
def session_scope(access_context: AccessContext | None = None) -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        if access_context is not None:
            _apply_access_context(session, access_context)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if access_context is not None:
            _reset_access_context(session)
        session.close()
