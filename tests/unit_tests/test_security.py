from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from tenauth.fastapi import require_auth
from tenauth.schemas import AuthContext


def _build_token(*, user_id: str | None = None, tenant_id: str | None = None) -> str:
    payload = {
        'sub': user_id or str(uuid4()),
        'tid': tenant_id or str(uuid4()),
    }
    header = (
        base64.urlsafe_b64encode(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode('utf-8')).decode('utf-8').rstrip('=')
    )
    body = base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8').rstrip('=')
    # Signature part may be empty; we keep trailing dot for readability
    return f'{header}.{body}.'


def _protected_app() -> FastAPI:
    app = FastAPI()

    @app.get('/protected')
    def protected(auth: AuthContext = Depends(require_auth)):
        return {'tenant_id': str(auth.tid), 'user_id': str(auth.sub)}

    return app


@pytest.fixture
def protected_client() -> Iterator[TestClient]:
    client = TestClient(_protected_app())
    yield client
    client.close()


def test_missing_authorization_header_returns_401(protected_client: TestClient):
    response = protected_client.get('/protected')
    assert response.status_code == 401
    assert response.json()['detail'] == 'Missing Authorization header'


def test_invalid_scheme_returns_401(protected_client: TestClient):
    token = _build_token()
    response = protected_client.get('/protected', headers={'Authorization': f'Basic {token}'})
    assert response.status_code == 401
    assert response.json()['detail'] == 'Missing Authorization header'


def test_malformed_token_returns_401(protected_client: TestClient):
    response = protected_client.get('/protected', headers={'Authorization': 'Bearer invalid-token'})
    assert response.status_code == 401
    assert response.json()['detail'] == 'Invalid token'


def test_valid_token_allows_access(protected_client: TestClient):
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    token = _build_token(user_id=user_id, tenant_id=tenant_id)
    response = protected_client.get('/protected', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.json() == {'tenant_id': tenant_id, 'user_id': user_id}
