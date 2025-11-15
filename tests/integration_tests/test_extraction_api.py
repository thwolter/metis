from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from datasifter.schemas import Candidate, RetrievalMetadata
from httpx import AsyncClient
from sqlmodel import select

from extraction.adapters.map_engine import MapEngine
from extraction.models import ExtractedAttribute, ExtractionJobStatus
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

    monkeypatch.setattr(MapEngine, 'extract_candidate', _fake_extract)


class _CrossLoopEvent:
    """Thread-safe event with an asyncio-friendly interface."""

    def __init__(self):
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._event.wait)


@pytest.fixture
def slow_map_extractor(monkeypatch: pytest.MonkeyPatch):
    started = _CrossLoopEvent()
    unblock = _CrossLoopEvent()

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

    monkeypatch.setattr(MapEngine, 'extract_candidate', _slow_extract)
    return started, unblock


@pytest.mark.asyncio
async def test_slow_map_extractor_waits_for_unblock(slow_map_extractor):
    started, unblock = slow_map_extractor
    extractor = MapEngine(model_name='test-model', llm=SimpleNamespace(ainvoke=lambda *_args, **_kwargs: None))
    attribute = SimpleNamespace(name='company_name')
    chunk = SimpleNamespace(
        chunk_id='chunk-1',
        header='header',
        page=1,
        retr_score=0.75,
        text='stub chunk text',
    )

    task = asyncio.create_task(
        extractor.extract_candidate(
            doc_type='annual_report',
            attribute=attribute,  # type: ignore[arg-type]
            chunk=chunk,  # type: ignore[arg-type]
            attempt=1,
        ),
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
    except asyncio.TimeoutError as exc:
        raise AssertionError('slow extractor never started') from exc
    await asyncio.sleep(0)  # allow the task to reach the blocking wait
    assert not task.done(), 'slow extractor unexpectedly finished before unblock'

    unblock.set()
    candidate = await asyncio.wait_for(task, timeout=1.0)
    assert candidate.attribute == attribute.name
    assert candidate.value == 'stubbed-value'
    assert candidate.retrieval.chunk_id == chunk.chunk_id


async def _poll_job_status(client: AsyncClient, job_id: UUID, *, timeout: float = 2) -> dict:
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


async def test_run_extraction_persists_results(
    auth_client: AsyncClient,
    auth_session,
    stub_map_extractor,
    dramatiq_worker,
):
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


async def test_cancel_extraction_job(
    auth_client: AsyncClient,
    auth_session,
    slow_map_extractor,
    dramatiq_worker,
):
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
    try:
        await asyncio.wait_for(started.wait(), timeout=5.0)
    except asyncio.TimeoutError as exc:
        raise AssertionError('Extraction job did not start in time') from exc
    try:
        # Production-faithful: cancel should be non-blocking and return quickly
        cancel_response = await auth_client.post(
            f'/v1/extraction/jobs/{job_id}/cancel',
            timeout=3.0,
        )
    finally:
        # Ensure the slow extractor can proceed and observe cancellation
        unblock.set()

    assert cancel_response.status_code == 202
    cancel_payload = cancel_response.json()
    assert cancel_payload['status'] in {
        ExtractionJobStatus.CANCELED.value,
        getattr(ExtractionJobStatus, 'CANCELLING').value
        if hasattr(ExtractionJobStatus, 'CANCELLING')
        else ExtractionJobStatus.CANCELED.value,
    }
    status_payload = await _poll_job_status(auth_client, job_id)
    assert status_payload['status'] == ExtractionJobStatus.CANCELED.value
    assert status_payload['results'] is None or status_payload['results'] == {}

    stmt = select(ExtractedAttribute).where(ExtractedAttribute.job_id == job_id)
    rows = (await auth_session.exec(stmt)).all()
    assert rows == []


def test_stream_reports_completion(sync_client, stub_map_extractor, dramatiq_worker):
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


async def test_extraction_job_waits_for_worker(
    auth_client: AsyncClient,
    stub_map_extractor,
    dramatiq_worker_controller,
):
    payload = {
        'doc_id': str(uuid4()),
        'doc_type': 'annual_report',
        'digest': DIGEST,
        'collection_name': COLLECTION,
        'attributes': ['company_name'],
        'dry_run': False,
    }

    # Ensure no worker is running so the message stays queued.
    dramatiq_worker_controller.stop()
    response = await auth_client.post('/v1/extraction/run', json=payload)
    job_id = UUID(response.json()['job_id'])

    queued_status = await auth_client.get(f'/v1/extraction/jobs/{job_id}')
    assert queued_status.json()['status'] == ExtractionJobStatus.QUEUED.value

    # Start the worker and verify the task completes.
    dramatiq_worker_controller.start()
    final_status = await _poll_job_status(auth_client, job_id)
    assert final_status['status'] == ExtractionJobStatus.COMPLETED.value
    assert final_status['results']['company_name']['value'] == 'SEFE Storage GmbH'
