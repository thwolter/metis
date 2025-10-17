from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
from typing import Any, cast

from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from metadata import models  # noqa: F401  # ensure models import for metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

project_root = Path(__file__).resolve().parent.parent
migration_env_path = project_root / '.env'
env_values = dotenv_values(migration_env_path) if migration_env_path.exists() else {}

alembic_url = env_values.get('ALEMBIC_DATABASE_URL') or os.getenv('ALEMBIC_DATABASE_URL')
if alembic_url is None:
    raise RuntimeError(
        'ALEMBIC_DATABASE_URL must be defined in .env.migration or the environment for alembic migrations.'
    )

config.set_main_option('sqlalchemy.url', alembic_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table='alembic_version',
        version_table_schema='metadata',
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = cast(dict[str, Any], config.get_section(config.config_ini_section) or {})
    connectable = engine_from_config(section, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table='alembic_version',
            version_table_schema='metadata',
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
