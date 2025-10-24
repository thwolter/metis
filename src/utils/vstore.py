from uuid import UUID

import psycopg2
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from psycopg2 import sql
from tenauth.tenancy import dsn_with_tenant

from core.config import get_settings

settings = get_settings()


def _normalize_psycopg_dsn(dsn: str) -> str:
    """Strip SQLAlchemy driver hints so psycopg2 accepts the URI."""
    scheme, sep, rest = dsn.partition('://')
    if sep and '+' in scheme:
        scheme = scheme.split('+', 1)[0]
        return f'{scheme}{sep}{rest}'
    return dsn


def pg_connect(tenant_id: UUID):
    dsn = settings.pg_vector_url.get_secret_value()
    tenant_dsn = dsn_with_tenant(dsn, tenant_id)
    psycopg_dsn = _normalize_psycopg_dsn(tenant_dsn)
    return psycopg2.connect(psycopg_dsn)


def get_collection_uuid(conn, collection_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                SELECT uuid
                FROM {}.langchain_pg_collection
                WHERE name = %s
                """
            ).format(sql.Identifier(settings.pg_vector_schema)),
            (collection_name,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f'Collection not found: {collection_name}')
        return row[0]


def get_vectorstore(*, collection_name: str, tenant_id: UUID) -> PGVector:
    """Create and return a PGVector instance lazily.

    This avoids importing DB drivers or creating connections at module import time,
    which helps tests and local dev that only import the graph.
    """
    dsn = settings.pg_vector_url.get_secret_value()
    tenant_dsn = dsn_with_tenant(dsn, tenant_id)
    embeddings = OpenAIEmbeddings(model='text-embedding-3-small')
    return PGVector(embeddings=embeddings, collection_name=collection_name, connection=tenant_dsn)
