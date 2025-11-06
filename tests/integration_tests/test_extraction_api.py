from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select

from extraction.map_step import MapExtractor
from extraction.models import ExtractedAttribute, ExtractionJobStatus
from extraction.schemas import Candidate, RetrievalMetadata
from tests.utils import load_fixtures  # type: ignore[import]

pytestmark = pytest.mark.integration

DIGEST = 'ks4K+uaD5QCsFla+ySvya1Arus2c/iRjr+JP4q/DP9s='
COLLECTION = 'default'


@pytest.fixture(scope='module', autouse=True)
def seed_vectra_fixtures():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')


@pytest.fixture
def stub_map_extractor(monkeypatch: pytest.MonkeyPatch):
    async def _fake_extract(
        self,
        *,
        doc_type: str,
        attribute,
        chunk,
        attempt: int = 1,
        prompt_id: str | None = None,
    ) -> Candidate:
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

    monkeypatch.setattr(MapExtractor, 'extract_candidate', _fake_extract)


@pytest.fixture
def slow_map_extractor(monkeypatch: pytest.MonkeyPatch):
    started = asyncio.Event()
    unblock = asyncio.Event()

    async def _slow_extract(
        self,
        *,
        doc_type: str,
        attribute,
        chunk,
        attempt: int = 1,
        prompt_id: str | None = None,
    ) -> Candidate:
        started.set()
        await unblock.wait()
        retrieval = RetrievalMetadata(
            chunk_id=chunk.chunk_id,
            header=chunk.header,
            page=chunk.page,
            retr_score=chunk.retr_score,
            text_excerpt=chunk.text[:320],
        )
        return Candidate(
            attribute=attribute.name,
            value='stubbed-value',
            confidence_local=0.8,
            rationale='slow stub',
            retrieval=retrieval,
            raw_json={'value': 'stubbed-value'},
        )

    monkeypatch.setattr(MapExtractor, 'extract_candidate', _slow_extract)
    return started, unblock


async def _poll_job_status(client: AsyncClient, job_id: UUID, *, timeout: float = 2.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        response = await client.get(f'/v1/extraction/jobs/{job_id}')
        response.raise_for_status()
        payload = response.json()
        if payload['status'] in {
            ExtractionJobStatus.COMPLETED.value,
            ExtractionJobStatus.FAILED.value,
            ExtractionJobStatus.CANCELED.value,
        }:
            return payload
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError('Timed out waiting for extraction job to finish')
        await asyncio.sleep(0.05)


async def test_run_extraction_persists_results(auth_client: AsyncClient, auth_session, stub_map_extractor):
    doc_id = uuid4()
    payload = {
        'doc_id': str(doc_id),
        'doc_type': 'annual_report',
        'digest': DIGEST,
        'collection_name': COLLECTION,
        'attributes': ['company_name', 'register_number'],
        'dry_run': False,
    }

    response = await auth_client.post('/v1/extraction/run', json=payload)
    assert response.status_code == 202
    job_data = response.json()
    job_id = UUID(job_data['job_id'])

    status_payload = await _poll_job_status(auth_client, job_id)
    assert status_payload['status'] == ExtractionJobStatus.COMPLETED.value
    assert status_payload['results']['company_name']['value'] == 'SEFE Storage GmbH'
    assert status_payload['results']['register_number']['value'] == 'HRB 18372'

    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == job_id)
    rows = (await auth_session.exec(stmt)).all()
    assert {row.attribute for row in rows} == {'company_name', 'register_number'}
    values = {row.attribute: row.value_json['value'] for row in rows if row.value_json}
    assert values == {'company_name': 'SEFE Storage GmbH', 'register_number': 'HRB 18372'}


async def test_cancel_extraction_job(auth_client: AsyncClient, auth_session, slow_map_extractor):
    started, unblock = slow_map_extractor
    doc_id = uuid4()
    payload = {
        'doc_id': str(doc_id),
        'doc_type': 'annual_report',
        'digest': DIGEST,
        'collection_name': COLLECTION,
        'attributes': ['company_name'],
        'dry_run': False,
    }

    response = await auth_client.post('/v1/extraction/run', json=payload)
    job_id = UUID(response.json()['job_id'])

    await asyncio.wait_for(started.wait(), timeout=1.0)

    cancel_response = await auth_client.post(f'/v1/extraction/jobs/{job_id}/cancel')
    assert cancel_response.status_code == 202
    assert cancel_response.json()['status'] == ExtractionJobStatus.CANCELED.value

    unblock.set()

    status_payload = await _poll_job_status(auth_client, job_id)
    assert status_payload['status'] == ExtractionJobStatus.CANCELED.value
    assert status_payload['results'] is None or status_payload['results'] == {}

    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == job_id)
    rows = (await auth_session.exec(stmt)).all()
    assert rows == []


def test_stream_reports_completion(sync_client, stub_map_extractor):
    doc_id = uuid4()
    payload = {
        'doc_id': str(doc_id),
        'doc_type': 'annual_report',
        'digest': DIGEST,
        'collection_name': COLLECTION,
        'attributes': ['company_name'],
        'dry_run': False,
    }

    response = sync_client.post('/v1/extraction/run', json=payload)
    assert response.status_code == 202
    job_id = response.json()['job_id']

    events: list[dict] = []
    with sync_client.websocket_connect(f'/v1/jobs/{job_id}/stream') as ws:
        while True:
            message = ws.receive_json()
            events.append(message)
            if message['event'] in {'job.completed', 'job.failed', 'job.canceled'}:
                break

    assert any(evt['event'] == 'job.started' for evt in events)
    final = events[-1]
    assert final['event'] == 'job.completed'
    assert final['results']['company_name']['value'] == 'SEFE Storage GmbH'
