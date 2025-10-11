import importlib
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings
from core.db import get_session
from metadata.models import DocumentMetadata, Job


class _DummyBroker:
    actor_options = set()
    actors: dict = {}

    def __init__(self, *args, **kwargs):
        self.client = SimpleNamespace(connection_pool=SimpleNamespace(connection_kwargs={}))

    def __getattr__(self, _name):
        def _noop(*_args, **_kwargs):
            return None

        return _noop


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    # Ensure settings pick up test configuration and prevent real broker setup.
    monkeypatch.setenv('INTERNAL_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')
    monkeypatch.setenv('POSTGRES_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')
    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'manual-metadata')
    get_settings.cache_clear()

    for module in ('metadata.tasks', 'metadata.api', 'main', 'core.queueing'):
        sys.modules.pop(module, None)

    redis_module = importlib.import_module('dramatiq.brokers.redis')
    monkeypatch.setattr(redis_module, 'RedisBroker', _DummyBroker)

    queueing = importlib.import_module('core.queueing')
    monkeypatch.setattr(queueing, '_make_broker', lambda: _DummyBroker())
    monkeypatch.setattr(queueing, 'setup_broker', lambda: None)
    monkeypatch.setattr(queueing, 'broker', _DummyBroker())

    main = importlib.import_module('main')
    app = main.create_app()

    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )

    original_job_schema = Job.__table__.schema  # type: ignore[missing-attribute]
    original_doc_schema = DocumentMetadata.__table__.schema  # type: ignore[missing-attribute]
    Job.__table__.schema = None  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = None  # type: ignore[missing-attribute]

    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client

    SQLModel.metadata.drop_all(engine)
    Job.__table__.schema = original_job_schema  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = original_doc_schema  # type: ignore[missing-attribute]
    get_settings.cache_clear()


def test_put_metadata_creates_versions(client):
    document_id = uuid4()
    headers = {'X-Internal-Auth': 'test-token'}

    payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME AG',
        }
    }

    response = client.put(f'/v1/documents/{document_id}/metadata', json=payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 1
    assert body['metadata']['company_name'] == 'ACME AG'

    updated_payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME Group',
            'reporting_year': 2024,
        }
    }

    response = client.put(f'/v1/documents/{document_id}/metadata', json=updated_payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 2
    assert body['metadata']['company_name'] == 'ACME Group'
    assert body['metadata']['reporting_year'] == 2024
