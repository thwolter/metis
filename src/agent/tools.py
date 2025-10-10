from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from psycopg2.extras import RealDictCursor

from core.config import get_settings
from utils.vstore import get_collection_uuid, get_vectorstore, pg_connect

from .schemas import ContextSchema

settings = get_settings()


@tool('first_chunks')
def first_chunks(
    config: RunnableConfig,
    k: int = 3,
    skip: int = 0,
) -> Document:
    """Fetch the next `k` chunks for the current digest via SQL, ordered by chunk id and return as a single document.

    :param config: Runnable configuration that carries digest context.
    :param k: Number of chunks to return.
    :param skip: Number of matching chunks to skip before returning results.

    """

    context = ContextSchema.model_validate(config['configurable'])
    if not context.digest or not context.collection_name:
        return Document(page_content='')

    limit = max(int(k), 0)
    offset = max(int(skip), 0)
    if limit == 0:
        return Document(page_content='')

    with pg_connect(tenant_id=context.tenant_id) as conn:
        collection_uuid = get_collection_uuid(conn, context.collection_name)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT document, cmetadata
                FROM langchain_pg_embedding
                WHERE collection_id = %s
                  AND cmetadata ->> 'digest' = %s
                ORDER BY (cmetadata ->> 'chunk_id')::int ASC
                LIMIT %s OFFSET %s
                """,
                (collection_uuid, context.digest, limit, offset),
            )
            rows = cur.fetchall()

    # Map rows to LangChain Document objects
    return Document(
        page_content='\n\n'.join([row['document'] for row in rows]),
        metadata={'file_name': rows[0]['cmetadata']['source']},
    )


@tool('retriever')
def retriever(
    query: str,
    config: RunnableConfig,
    **kwargs,
) -> Document:
    """Retrieve documents by semantic search and return as a single document.

    :param config:
    :param query: Natural-language search terms only (what the user wants to find). Do NOT include any digest or document IDs here.

    """
    context = ContextSchema.model_validate(config['configurable'])
    if not kwargs:
        kwargs = {}
    kwargs.setdefault('filter', {'digest': context.digest})

    vs = get_vectorstore(collection_name=context.collection_name, tenant_id=context.tenant_id)
    docs = vs.search(query, 'similarity', **kwargs)
    return Document(page_content='\n\n'.join([doc.page_content for doc in docs]))


search_tool = tool = TavilySearch(
    tavily_api_key=settings.tavily_api_key.get_secret_value(),
    max_results=5,
    topic='general',
)
