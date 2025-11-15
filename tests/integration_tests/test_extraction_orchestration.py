from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from datasifter.interfaces import MapEngine
from datasifter.schemas import Candidate, ExtractionRequest, RetrievalMetadata
from sqlmodel import select

from extraction.models import ExtractedAttribute
from extraction.runner import build_runner
from tests.utils import load_fixtures  # type: ignore[import]

pytestmark = pytest.mark.integration

DIGEST = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='
COLLECTION = 'default'
TENANT_ID = UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde')


@pytest.fixture(scope='module', autouse=True)
def seed_vectra_fixtures():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')


class FakeMapEngine(MapEngine):
    def __init__(self) -> None:
        self.calls: int = 0

    async def extract_candidate(
        self,
        *,
        doc_type: str,
        attribute,
        chunk,
        attempt: int,
        prompt_id: str | None = None,
    ) -> Candidate:
        del doc_type, attempt, prompt_id
        self.calls += 1
        mapping = {
            'company_name': 'SEFE Storage GmbH',
            'register_number': 'HRB 18372',
        }
        value = mapping.get(attribute.name, f'stub-{attribute.name}')
        retrieval = RetrievalMetadata(
            chunk_id=chunk.chunk_id,
            header=chunk.header,
            page=chunk.page,
            retr_score=chunk.retr_score,
            text_excerpt=chunk.text[:320],
        )
        return Candidate(
            attribute=attribute.name,
            value=value,
            confidence_local=0.92,
            rationale='stubbed candidate',
            retrieval=retrieval,
            raw_json={'value': value, 'confidence': 0.92},
        )


@pytest.mark.asyncio
async def test_runner_persists_attributes(auth_session):
    fake_engine = FakeMapEngine()

    def _engine_factory(_: str) -> MapEngine:
        return fake_engine

    runner = build_runner(auth_session, map_engine_factory=_engine_factory)
    request = ExtractionRequest(
        doc_id=uuid4(),
        doc_type='annual_report',
        tenant_id=TENANT_ID,
        digest=DIGEST,
        collection_name=COLLECTION,
        attributes=['company_name', 'register_number'],
        dry_run=False,
    )

    outcome = await runner.run(request)

    assert outcome.result.errors == []
    assert outcome.result.attributes['company_name'].value == 'SEFE Storage GmbH'
    assert outcome.result.attributes['register_number'].value == 'HRB 18372'
    assert fake_engine.calls > 0

    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == outcome.result.job_id)
    rows = (await auth_session.exec(stmt)).all()
    values = {row.attribute: row.value_json['value'] for row in rows if row.value_json}
    assert values == {'company_name': 'SEFE Storage GmbH', 'register_number': 'HRB 18372'}
