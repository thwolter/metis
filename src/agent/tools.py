from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from core.config import get_settings
from core.db import pg_connect
from utils.vstore import VECTOR_SCHEMA, get_collection_uuid, get_vectorstore

from .schemas import ContextSchema

settings = get_settings()


async def get_rows(limit: int, *, context: ContextSchema, offset: int = 0) -> list:
    conn = await pg_connect(tenant_id=context.tenant_id)
    try:
        collection_uuid = await get_collection_uuid(conn, context.collection_name)
        query = f"""
            SELECT document, cmetadata
            FROM {VECTOR_SCHEMA}.langchain_pg_embedding
            WHERE collection_id = $1
              AND cmetadata ->> 'digest' = $2
            ORDER BY (cmetadata ->> 'chunk_id')::int ASC
            LIMIT $3 OFFSET $4
        """
        rows = await conn.fetch(query, collection_uuid, context.digest, limit, offset)
    finally:
        await conn.close()
    return rows


@tool('first_chunks')
async def first_chunks(
    config: RunnableConfig,
    k: int = 3,
    skip: int = 0,
) -> Document:
    """Fetch the next `k` chunks for the current digest via SQL, ordered by chunk id and return as a single document."""

    context = ContextSchema.model_validate(config['configurable'])
    if not context.digest or not context.collection_name:
        return Document(page_content='')

    offset = max(int(skip), 0)
    if limit := max(int(k), 0) == 0:
        return Document(page_content='')

    rows = await get_rows(limit, context=context, offset=offset)
    if not rows:
        return Document(page_content='')

    metadata_value = rows[0]['cmetadata']
    metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
    file_name = metadata.get('source')
    page_content = '\n\n'.join(row['document'] for row in rows)
    return Document(
        page_content=page_content,
        metadata={'file_name': file_name} if file_name else {},
    )


@tool('retriever')
async def retriever(
    query: str,
    config: RunnableConfig,
    exclude_chunk_ids: list[int] | None = None,
) -> Document:
    """Retrieve documents by semantic search and return as a single document.

    :param config:
    :param query: Natural-language search terms only (what the user wants to find). Do NOT include any digest or document IDs here.
    :param exclude_chunk_ids: exclude these chunk IDs from the search results

    """
    context = ContextSchema.model_validate(config['configurable'])
    search_kwargs = {
        'filter': {'$and': [{'digest': {'$eq': context.digest}}, {'chunk_id': {'$nin': exclude_chunk_ids or []}}]}
    }

    vs = get_vectorstore(collection_name=context.collection_name, tenant_id=context.tenant_id)
    docs = await vs.asearch(query, 'similarity', **search_kwargs)
    return Document(page_content='\n\n'.join(doc.page_content for doc in docs))
