import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.security import INTERNAL_AUTH_HEADER, require_internal_auth


def _protected_app() -> FastAPI:
    app = FastAPI()

    @app.get('/protected', dependencies=[Depends(require_internal_auth)])
    def protected():
        return {'status': 'ok'}

    return app


@pytest.fixture
def protected_client(monkeypatch: pytest.MonkeyPatch):
    token = 'secret-token'
    get_settings.cache_clear()
    monkeypatch.setenv('INTERNAL_AUTH_TOKEN', token)
    client = TestClient(_protected_app())
    yield client, token
    client.close()
    get_settings.cache_clear()


def test_missing_token_rejected(protected_client):
    client, _ = protected_client
    response = client.get('/protected')
    assert response.status_code == 401


def test_invalid_token_rejected(protected_client):
    client, _ = protected_client
    response = client.get('/protected', headers={INTERNAL_AUTH_HEADER: 'wrong'})
    assert response.status_code == 401


def test_valid_token_allowed(protected_client):
    client, token = protected_client
    response = client.get('/protected', headers={INTERNAL_AUTH_HEADER: token})
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
