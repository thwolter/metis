from __future__ import annotations

import base64
import json
from typing import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from tenauth.schemas import AccessContext, AuthContext

from core.db import scoped_session
from main import app
from metadata.models import Job, JobStatus, utc_now
from metadata.service import get_job, set_job_status

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


async def _set_job_status(job_id: UUID, status: JobStatus, access: AccessContext) -> None:
    async with scoped_session(access_context=access) as session:
        job = await session.get(Job, job_id)
        assert job is not None, 'Expected job to exist for status update'

        job.status = status
        now = utc_now()
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
            job.finished_at = now


def make_bearer_token(ctx: AuthContext) -> str:
    """Return a JWT-like Bearer token (no signature) from an AuthContext."""
    header = {'alg': 'none'}
    payload = {
        'sub': str(ctx.sub),
        'tid': str(ctx.tid),
        'role': ctx.role,
        'scopes': ctx.scopes,
        'plan': ctx.plan,
        'iat': ctx.iat,
        'exp': ctx.exp,
        'iss': ctx.iss,
        'aud': ctx.aud,
    }
    # remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    def b64(data: dict) -> str:
        raw = json.dumps(data, separators=(',', ':')).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip('=')

    token = f'{b64(header)}.{b64(payload)}.'
    return f'Bearer {token}'


ctx = AuthContext(
    sub=UUID('00000000-0000-0000-0000-000000000000'),
    tid=UUID('00000000-0000-0000-0000-000000000000'),
    role='owner',
    scopes=['documents:read'],
)


@pytest.fixture(scope='session')
def sync_client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def test_job_status_stream_emits_updates(sync_client: TestClient) -> None:
    response = sync_client.post('/v1/metadata', json=_job_request_body())
    assert response.status_code == 202
    payload = response.json()

    job_id = payload['job_id']
    document_id = payload['document_id']
    access = AccessContext(tenant_id=ctx.tid, user_id=ctx.sub)

    stream_path = f'/v1/jobs/{job_id}/stream'

    async def _advance_status(job_id: UUID, status: JobStatus, access: AccessContext) -> None:
        async with scoped_session(access_context=access) as session:
            job = await get_job(session, job_id)
            if job:
                await set_job_status(session, job, status)

    def set_status(job_id: UUID, status: JobStatus) -> None:
        # Run entirely inside TestClient's AnyIO portal to avoid cross-loop sessions
        sync_client.portal.call(_advance_status, job_id, status, access)  # type: ignore[missing-attribute]

    with sync_client.websocket_connect(stream_path, headers={'Authorization': make_bearer_token(ctx)}) as ws:
        first = ws.receive_json()
        assert first['status'] == JobStatus.QUEUED.value

        set_status(UUID(job_id), JobStatus.SUCCEEDED)
        third = ws.receive_json()
        assert third['status'] == JobStatus.SUCCEEDED.value
        assert third['result_url'].endswith(f'/v1/documents/{document_id}/metadata?version=latest')
