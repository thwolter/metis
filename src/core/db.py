from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from core.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.pg_vector_url.get_secret_value()
        _engine = create_engine(url, echo=settings.debug or False, pool_pre_ping=True, pool_recycle=3600)
    return _engine


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session
