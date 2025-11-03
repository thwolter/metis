from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import urlparse
from uuid import UUID

import pytest
from langchain_core.documents import Document
from langchain_core.runnables.config import RunnableConfig

from agent.schemas import ContextSchema
from agent.tools import first_chunks, get_rows, retriever


def _config_for_context(context: ContextSchema) -> RunnableConfig:
    """Render the context into the structure expected by LangChain tools."""
    return {'configurable': context.model_dump(mode='json')}


def _default_context() -> ContextSchema:
    return ContextSchema(
        digest='vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc=',
        collection_name='default',
        tenant_id=UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde'),
    )


def _load_fixtures(name: str):
    def _extract_host_port(dsn: str) -> tuple[str, int | None]:
        parsed = urlparse(dsn)
        host = parsed.hostname or 'localhost'
        port = parsed.port
        return host, port

    host, port = _extract_host_port(os.environ['POSTGRES_URL'])
    env = os.environ.copy()
    env['PGPASSWORD'] = 'test'

    subprocess.run(
        ['psql', '-h', str(host), '-p', str(port), '-U', 'test', '-d', 'test', '-f', name],
        check=True,
        env=env,
    )


@pytest.fixture(scope='session', autouse=True)
def load_vectra_data():
    _load_fixtures('tests/fixtures/vectra_roles.sql')
    _load_fixtures('tests/fixtures/vectra_fixtures.sql')


async def test_get_rows_returns_expected_rows() -> None:
    result = await get_rows(3, context=_default_context())

    for i in range(3):
        assert json.loads(result[i]['cmetadata'])['chunk_id'] == i


# todo: fix
async def test_first_chunks_returns_expected_document() -> None:
    context = _default_context()

    result = await first_chunks.ainvoke({}, config=_config_for_context(context))

    assert result.metadata == {'file_name': 'sefe-storage-gmbh-jahresabschluss-und-lagebericht-2024.pdf'}
    assert result.page_content.startswith('# Lagebericht f\u00fcr das Gesch\u00e4ftsjahr 2024')
    assert 'Bundesf\u00f6rderung Industrie und Klimaschutz' in result.page_content


# todo: fix
async def test_first_chunks_applies_skip_offset() -> None:
    context = _default_context()

    result = await first_chunks.ainvoke({'k': 1, 'skip': 1}, config=_config_for_context(context))

    assert result.metadata == {'file_name': 'sefe-storage-gmbh-jahresabschluss-und-lagebericht-2024.pdf'}
    assert result.page_content.startswith(
        '# Lagebericht f\u00fcr das Gesch\u00e4ftsjahr vom 1. Januar bis 31. Dezember 2024'
    )
    assert 'Transformation hin zu erneuerbarem Strom' in result.page_content


# todo: fix
async def test_first_chunks_returns_empty_document_when_digest_missing() -> None:
    context = ContextSchema(
        digest='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
        collection_name='default',
        tenant_id=UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde'),
    )

    result = await first_chunks.ainvoke({'k': 3}, config=_config_for_context(context))

    assert result.page_content == ''
    assert result.metadata == {}


# todo: fix
async def test_retriever_builds_filter_and_combines_results(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _default_context()
    captured_kwargs: dict[str, UUID | str] = {}
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeVectorStore:
        async def asearch(self, query: str, search_type: str, **kwargs: object) -> list[Document]:
            calls.append((query, search_type, kwargs))
            return [Document(page_content='chunk-one'), Document(page_content='chunk-two')]

    fake_store = FakeVectorStore()

    def _fake_get_vectorstore(*, collection_name: str, tenant_id: UUID) -> FakeVectorStore:
        captured_kwargs['collection_name'] = collection_name
        captured_kwargs['tenant_id'] = tenant_id
        return fake_store

    monkeypatch.setattr('agent.tools.get_vectorstore', _fake_get_vectorstore)

    result = await retriever.ainvoke(
        {'query': 'find relevant context', 'exclude_chunk_ids': [1, 2]},
        config=_config_for_context(context),
    )

    assert captured_kwargs == {
        'collection_name': 'default',
        'tenant_id': UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde'),
    }
    assert calls == [
        (
            'find relevant context',
            'similarity',
            {'filter': {'$and': [{'digest': {'$eq': context.digest}}, {'chunk_id': {'$nin': [1, 2]}}]}},
        )
    ]
    assert result.page_content == 'chunk-one\n\nchunk-two'
    assert result.metadata == {}
