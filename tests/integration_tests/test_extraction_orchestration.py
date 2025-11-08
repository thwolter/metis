from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from core.config import get_settings
from extraction.graph.context import ExtractionContext
from extraction.graph.orchestration import _prepare_job, _process_attribute
from extraction.graph.progress import AttributeState, ProgressTracker
from extraction.graph.status import StatusEmitter
from extraction.models import ExtractedAttribute
from extraction.registry.registry import get_attribute_specs
from extraction.schemas import Candidate, ExtractionRequest, RetrievalMetadata
from extraction.tools.map_step import MapExtractor
from extraction.utils import resolve_execution_config
from tests.utils import load_fixtures  # type: ignore[import]

pytestmark = pytest.mark.integration

DIGEST = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='
COLLECTION = 'default'
TENANT_ID = UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde')


@pytest.fixture(scope='module', autouse=True)
def seed_vectra_fixtures():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')


@pytest.fixture()
def stub_openai_embeddings(monkeypatch: pytest.MonkeyPatch):
    class FakeEmbeddings:
        def __init__(self, *args, **kwargs):
            self._dimension = 1536

        def embed_query(self, _: str) -> list[float]:
            return [0.0] * self._dimension

        async def aembed_query(self, text: str) -> list[float]:
            return self.embed_query(text)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * self._dimension for _ in texts]

        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            return self.embed_documents(texts)

    monkeypatch.setattr('utils.vstore.OpenAIEmbeddings', FakeEmbeddings)


async def test_process_attribute_persists_company_name(auth_session, stub_openai_embeddings):
    settings = get_settings()
    request = ExtractionRequest(
        doc_id=uuid4(),
        doc_type='annual_report',
        tenant_id=TENANT_ID,
        digest=DIGEST,
        collection_name=COLLECTION,
        attributes=['company_name'],
        dry_run=False,
    )
    retrieval_config = resolve_execution_config(settings, request)
    job = await _prepare_job(auth_session, request, None, retrieval_config, settings)

    attr_spec = get_attribute_specs('annual_report', ['company_name'])[0]
    progress = ProgressTracker(total_attributes=1)
    attr_states = {attr_spec.name: AttributeState(attr_spec.name)}

    class FakeMapExtractor(MapExtractor):
        def __init__(self):
            self.calls = 0

        async def extract_candidate(
            self,
            *,
            doc_type: str,
            attribute,
            chunk,
            attempt: int = 1,
            prompt_id: str | None = None,
        ) -> Candidate:
            self.calls += 1
            retrieval = RetrievalMetadata(
                chunk_id=chunk.chunk_id,
                header=chunk.header,
                page=chunk.page,
                retr_score=chunk.retr_score,
                text_excerpt=chunk.text[:320],
            )
            return Candidate(
                attribute=attribute.name,
                value='SEFE Storage GmbH',
                confidence_local=0.92,
                rationale='stubbed candidate',
                retrieval=retrieval,
                raw_json={'value': 'SEFE Storage GmbH', 'confidence': 0.92},  # type: ignore[assignment]
            )

    fake_map_extractor = FakeMapExtractor()
    emitter = StatusEmitter(
        auth_session,
        job=job,
        doc_id=request.doc_id,
        doc_type=request.doc_type,
        callback=None,
        progress=progress,
        attribute_states=attr_states,
    )
    context = ExtractionContext(
        session=auth_session,
        request=request,
        job=job,
        retrieval_config=retrieval_config,
        collection_name=COLLECTION,
        digest=DIGEST,
        map_extractor=fake_map_extractor,
        emitter=emitter,
        progress=progress,
        attribute_states=attr_states,
    )

    result = await _process_attribute(context, attr_spec)

    assert fake_map_extractor.calls == attr_states[attr_spec.name].mapped
    assert result.name == 'company_name'
    assert result.value == 'SEFE Storage GmbH'
    assert result.status == 'accepted'
    assert result.chunk_count == attr_states[attr_spec.name].planned
    assert attr_states[attr_spec.name].state == 'persisted'

    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == job.job_id)
    persisted = (await auth_session.exec(stmt)).one()
    assert persisted.attribute == 'company_name'
    assert persisted.value_json is not None
    assert persisted.value_json['value'] == 'SEFE Storage GmbH'


@pytest.mark.skip(reason='requires OpenAI API key')
async def test_process_attribute_returns_correct_company_name(auth_session):
    settings = get_settings()
    request = ExtractionRequest(
        doc_id=uuid4(),
        doc_type='annual_report',
        tenant_id=TENANT_ID,
        digest=DIGEST,
        collection_name=COLLECTION,
        attributes=['company_name'],
        dry_run=False,
    )

    retrieval_config = resolve_execution_config(settings, request)
    job = await _prepare_job(auth_session, request, None, retrieval_config, settings)

    attr_spec = get_attribute_specs('annual_report', ['company_name'])[0]
    progress = ProgressTracker(total_attributes=1)
    attr_states = {attr_spec.name: AttributeState(attr_spec.name)}

    emitter = StatusEmitter(
        auth_session,
        job=job,
        doc_id=request.doc_id,
        doc_type=request.doc_type,
        callback=None,
        progress=progress,
        attribute_states=attr_states,
    )
    context = ExtractionContext(
        session=auth_session,
        request=request,
        job=job,
        retrieval_config=retrieval_config,
        collection_name=COLLECTION,
        digest=DIGEST,
        map_extractor=MapExtractor(),
        emitter=emitter,
        progress=progress,
        attribute_states=attr_states,
    )

    result = await _process_attribute(context, attr_spec)

    assert result.name == 'company_name'
    assert result.value == 'SEFE Storage GmbH'
    assert result.status == 'accepted'
    assert result.chunk_count == attr_states[attr_spec.name].planned
    assert attr_states[attr_spec.name].state == 'persisted'
