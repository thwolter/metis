from __future__ import annotations

import json
from uuid import UUID

import pytest
from langchain_core.documents import Document
from langchain_core.runnables.config import RunnableConfig

from agent.schemas import ContextSchema
from agent.tools import first_chunks, get_rows, retriever

from ..utils import load_fixtures  # type: ignore[missing-import]


def _config_for_context(context: ContextSchema) -> RunnableConfig:
    """Render the context into the structure expected by LangChain tools."""
    return {'configurable': context.model_dump(mode='json')}


def _default_context() -> ContextSchema:
    return ContextSchema(
        digest='vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc=',
        collection_name='default',
        tenant_id=UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde'),
    )


@pytest.fixture(scope='session', autouse=True)
def load_vectra_data():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')


async def test_get_rows_returns_expected_rows() -> None:
    result = await get_rows(3, context=_default_context())

    for i in range(3):
        assert json.loads(result[i]['cmetadata'])['chunk_id'] == i


@pytest.mark.skip(reason='fix')
async def test_first_chunks_returns_expected_document() -> None:
    context = _default_context()

    result = await first_chunks.ainvoke({}, config=_config_for_context(context))

    assert result.metadata == {'file_name': 'sefe-storage-gmbh-jahresabschluss-und-lagebericht-2024.pdf'}
    assert result.page_content.startswith('> SEFE logo (leaf-shaped icon) at top')
    assert 'Speicherzone Nord' in result.page_content


@pytest.mark.skip(reason='fix')
async def test_first_chunks_applies_skip_offset() -> None:
    context = _default_context()

    result = await first_chunks.ainvoke({'k': 1, 'skip': 1}, config=_config_for_context(context))

    assert result.metadata == {'file_name': 'sefe-storage-gmbh-jahresabschluss-und-lagebericht-2024.pdf'}
    assert result.page_content.startswith(
        '# Lagebericht f\u00fcr das Gesch\u00e4ftsjahr vom 1. Januar bis 31. Dezember 2024'
    )
    assert 'Transformation hin zu erneuerbarem Strom' in result.page_content


async def test_first_chunks_returns_empty_document_when_digest_missing() -> None:
    context = ContextSchema(
        digest='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
        collection_name='default',
        tenant_id=UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde'),
    )

    result = await first_chunks.ainvoke({'k': 3}, config=_config_for_context(context))

    assert result.page_content == ''
    assert result.metadata == {}


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
