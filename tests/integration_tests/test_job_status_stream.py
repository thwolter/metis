from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from tenauth.schemas import AccessContext

from core.db import scoped_session
from main import app
from metadata.models import Job, JobStatus, utc_now

pytestmark = pytest.mark.integration

TEST_DIGEST = 'A' * 43 + '='


def _job_request_body() -> dict[str, object]:
    return {
        'context': {
            'digest': TEST_DIGEST,
            'collection_name': 'integration-tests',
        },
        # Metadata is optional; omit to keep payload minimal.
        'profile': 'default',
    }


async def _set_job_status(job_id: UUID, status: JobStatus) -> None:
    ctx = AccessContext(tenant_id=tenant_id, user_id=user_id)
    async with scoped_session(access_context=ctx) as session:
        job = await session.get(Job, job_id)
        assert job is not None, 'Expected job to exist for status update'

        job.status = status
        now = utc_now()
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
            job.finished_at = now


def test_job_status_stream_emits_updates(auth_client) -> None:
    with TestClient(app) as client:
        response = client.post('/v1/metadata', json=_job_request_body())
        assert response.status_code == 202
        payload = response.json()

        job_id = payload['job_id']
        document_id = payload['document_id']

        stream_path = f'/v1/jobs/{job_id}/stream'

        with client.websocket_connect(stream_path) as websocket:
            first = websocket.receive_json()
            assert first['status'] == JobStatus.QUEUED.value

            asyncio.run(_set_job_status(UUID(job_id), JobStatus.RUNNING))
            second = websocket.receive_json()
            assert second['status'] == JobStatus.RUNNING.value

            asyncio.run(_set_job_status(UUID(job_id), JobStatus.SUCCEEDED))
            third = websocket.receive_json()
            assert third['status'] == JobStatus.SUCCEEDED.value
            assert third['result_url'].endswith(f'/v1/documents/{document_id}/metadata?version=latest')
