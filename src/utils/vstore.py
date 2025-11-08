from __future__ import annotations

import re
from typing import Final
from uuid import UUID

from asyncpg import Connection
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import DistanceStrategy

from core.config import get_settings

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _validate_schema(schema: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(schema):
        raise ValueError(f'invalid pgvector schema name {schema!r}')
    return schema


async def get_collection_uuid(conn: Connection, collection_name: str) -> str:
    settings = get_settings()
    vector_schema: Final[str] = _validate_schema(settings.pg_vector_schema)
    query = f"""
        SELECT uuid
        FROM {vector_schema}.langchain_pg_collection
        WHERE name = $1
    """
    row = await conn.fetchrow(query, collection_name)
    if row is None:
        raise ValueError(f'Collection not found: {collection_name}')

    uuid_value = str(row['uuid']).strip()
    if not uuid_value:
        raise ValueError('Collection has empty UUID value')
    return uuid_value


def get_vectorstore(*, collection_name: str, tenant_id: UUID) -> PGVector:
    """Create and return a PGVector instance lazily.

    This avoids importing DB drivers or creating connections at module import time,
    which helps tests and local dev that only import the graph.
    """
    settings = get_settings()
    dsn = settings.async_postgres_url.get_secret_value()
    embeddings = OpenAIEmbeddings(model='text-embedding-3-small')
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=dsn,
        async_mode=True,
        create_extension=False,
        distance_strategy=DistanceStrategy.COSINE,
        engine_args={
            'connect_args': {'server_settings': {'app.tenant_id': str(tenant_id), 'search_path': 'vectra,public'}}
        },
    )
