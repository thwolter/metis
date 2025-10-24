import asyncio
from uuid import UUID

from fastapi.testclient import TestClient
from tenauth.schemas import AccessContext

from core.db import scoped_session
from main import create_app
from metadata.models import Job, JobStatus

JWT_TOKEN = (
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
    'eyJzdWIiOiI1YTQxMDI2MS1iOTIzLTRjODktYWUzMC0yZWQwZDhmYzZiNmIiLCJ0aWQiOiI0MGQ5OTkwYS05YjlmLTQ3ZWEtYTcxMS0xNGYzMjYzYWFlNDYiLCJyb2xlIjoib3duZXIiLCJzY29wZXMiOltdLCJpYXQiOjE3NjEyMzY3MjQsImV4cCI6MTc2MTI0MDMyNH0.'
    'gmmFRkGHXJemBwHEUeR-reom4_qdjQy-yv-vTt3P0Kg'
)

TENANT_ID = '40d9990a-9b9f-47ea-a711-14f3263aae46'
USER_ID = '5a410261-b923-4c89-ae30-2ed0d8fc6b6b'


def test_create_metadata_job_e2e(refresh_settings):
    refresh_settings(reload_dotenv=True, dotenv_path='.env.test')

    digest = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='
    payload = {
        'context': {
            'digest': digest,
            'collection_name': 'default',
        }
    }

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            '/v1/metadata',
            json=payload,
            headers={'Authorization': f'Bearer {JWT_TOKEN}'},
        )

    assert response.status_code == 202
    body = response.json()
    assert 'job_id' in body
    assert 'document_id' in body
    assert body['status_url'].endswith(f'/v1/jobs/{body["job_id"]}')
    assert body['result_url'] is None

    access_context = AccessContext(tenant_id=UUID(TENANT_ID), user_id=UUID(USER_ID))

    async def _verify_job() -> None:
        async with scoped_session(access_context=access_context) as session:
            stored_job = await session.get(Job, UUID(body['job_id']))
            assert stored_job is not None
            assert stored_job.status == JobStatus.QUEUED
            assert str(stored_job.tenant_id) == TENANT_ID
            assert str(stored_job.user_id) == USER_ID
            assert stored_job.document_digest == digest
            assert stored_job.collection_name == 'annual-reports'

    asyncio.run(_verify_job())
