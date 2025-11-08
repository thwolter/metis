from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command
from alembic.config import Config
from core import db as core_db
from tests.utils import load_fixtures  # type: ignore[missing-import]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INIT_SQL_DIR = PROJECT_ROOT / 'docker' / 'init'
TEST_SEED_DIR = PROJECT_ROOT / 'tests' / 'fixtures' / 'init_sql'


async def _load_seed_data(connection_url: URL | None = None) -> None:
    if not TEST_SEED_DIR.exists():
        return

    for sql_path in sorted(TEST_SEED_DIR.glob('*.sql')):
        load_fixtures(str(sql_path))


async def reset_database_state() -> None:
    alembic_url = os.environ.get('ALEMBIC_DATABASE_URL')
    if not alembic_url:
        return

    engine = create_async_engine(alembic_url)
    try:
        async with AsyncSession(engine) as session:
            await session.exec(text('TRUNCATE TABLE metadata.document_metadata RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE metadata.documents RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE metadata.metadata_jobs RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE classification.class_prototypes RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE classification.classification_runs RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE classification.doc_classes RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.exec(text('TRUNCATE TABLE classification.header_weights RESTART IDENTITY CASCADE'))  # type: ignore[no-matching-overload]
            await session.commit()
            await _load_seed_data()
    finally:
        await engine.dispose()

    await core_db.dispose_engines()


async def _execute_sql_scripts(connection_url: URL, directory: Path) -> None:
    if not directory.exists():
        return

    for sql_path in sorted(directory.glob('*.sql')):
        load_fixtures(str(sql_path), url=connection_url)


async def prepare_database(base_url: URL) -> tuple[URL, URL]:
    print('Preparing database on port', base_url.port, '...')
    await _execute_sql_scripts(base_url, INIT_SQL_DIR)

    app_url = base_url.set(username='metis_app_user', password='app-user-password')
    alembic_url = base_url.set(username='metis_alembic_user', password='alembic-user-password')
    return app_url, alembic_url


def run_migrations() -> None:
    alembic_cfg = Config(str(PROJECT_ROOT / 'alembic.ini'))
    alembic_cfg.set_main_option('script_location', str(PROJECT_ROOT / 'alembic'))
    command.upgrade(alembic_cfg, 'head')
