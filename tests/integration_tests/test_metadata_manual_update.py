import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine
from tenauth.schemas import AccessContext

from core.config import get_settings
from metadata import api as metadata_api
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
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Ensure settings pick up test configuration and prevent real broker setup.
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('POSTGRES_URL', f'sqlite:///{db_path}')
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
        f'sqlite:///{db_path}',
        connect_args={'check_same_thread': False},
    )

    original_job_schema = Job.__table__.schema  # type: ignore[missing-attribute]
    original_doc_schema = DocumentMetadata.__table__.schema  # type: ignore[missing-attribute]
    Job.__table__.schema = None  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = None  # type: ignore[missing-attribute]

    Job.__table__.create(engine)  # type:ignore[missing-attribute]
    DocumentMetadata.__table__.create(engine)  # type:ignore[missing-attribute]

    tenant_id = uuid4()
    user_id = uuid4()

    def override_access_context():
        return AccessContext(tenant_id=tenant_id, user_id=user_id)

    def override_scoped_session():
        session = Session(engine)
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[metadata_api.require_access_context] = override_access_context
    app.dependency_overrides[metadata_api.get_scoped_session] = override_scoped_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    DocumentMetadata.__table__.drop(engine)  # type:ignore[missing-attribute]
    Job.__table__.drop(engine)  # type:ignore[missing-attribute]
    Job.__table__.schema = original_job_schema  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = original_doc_schema  # type: ignore[missing-attribute]
    get_settings.cache_clear()
    if db_path.exists():
        db_path.unlink()


def test_put_metadata_creates_versions(client):
    document_id = uuid4()
    payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME AG',
        }
    }

    response = client.put(f'/v1/documents/{document_id}/metadata', json=payload)
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

    response = client.put(f'/v1/documents/{document_id}/metadata', json=updated_payload)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 2
    assert body['metadata']['company_name'] == 'ACME Group'
    assert body['metadata']['reporting_year'] == 2024
