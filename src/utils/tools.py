from typing import List
from uuid import UUID

from langchain_core.documents import Document

from src.core.config import get_settings
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from src.core.tenancy import dsn_with_tenant

settings = get_settings()

embeddings = OpenAIEmbeddings(model='text-embedding-3-small')
collection_name = 'default'
dsn = settings.pg_vector_url.get_secret_value()
tenant_id = UUID('ae579baf-91c2-4497-abf5-44867e06c7a1')

tenant_dsn = dsn_with_tenant(dsn, tenant_id)

vs = PGVector(
    embeddings=embeddings,
    collection_name=collection_name,
    connection=tenant_dsn
)

def retrieve(query: str, **kwargs) -> List[Document]:
    return vs.search(query, 'similarity', **kwargs)