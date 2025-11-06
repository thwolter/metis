from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from classification.models import ClassPrototype
from tests.utils import load_fixtures  # type: ignore[import]

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module', autouse=True)
def include_classification_router():
    """Ensure the classification API routes are registered on the app under test."""
    from classification.api import router as classification_router
    from main import app

    has_routes = any(
        isinstance(route, APIRoute) and route.path.startswith('/api/classification') for route in app.routes
    )
    if not has_routes:
        app.include_router(classification_router)


@pytest.fixture(scope='module', autouse=True)
def seed_vectra_fixtures():
    """Vector store fixtures are persisted across classification DB resets."""
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')
    load_fixtures('vectra_classifier.sql')


async def test_recompute_dry_run_returns_stats(auth_client):
    payload = {
        'class_name': 'annual_report',
        'digests': ['vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='],
        'dry_run': True,
    }

    response = await auth_client.post('/api/classification/recompute', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['class_name'] == payload['class_name']
    assert data['dry_run'] is True
    assert data['updated'] is False
    assert data['n_docs'] >= 1
    assert data['centroid_dim'] == 1536
    assert data['dispersion'] >= 0.0


async def test_recompute_persists_prototype(auth_client, any_session):
    load_fixtures('classification.sql')
    payload = {
        'class_name': 'annual_report',
        'digests': ['vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='],
        'dry_run': False,
    }

    response = await auth_client.post('/api/classification/recompute', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['updated'] is True
    assert data['dry_run'] is False
    assert data['n_docs'] >= 1

    proto = await any_session.get(ClassPrototype, payload['class_name'])
    assert proto is not None
    assert proto.n_docs == data['n_docs']
    assert len(proto.centroid) == data['centroid_dim']


async def test_online_update_creates_prototype(auth_client, any_session):
    load_fixtures('classification.sql')
    payload = {
        'class_name': 'company_register',
        'digest': 'ks4K+uaD5QCsFla+ySvya1Arus2c/iRjr+JP4q/DP9s=',
        'dry_run': False,
        'ema_alpha': 0.3,
    }

    response = await auth_client.post('/api/classification/online-update', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['updated'] is True
    assert data['dry_run'] is False
    assert data['n_docs'] >= 1
    assert data['centroid_dim'] == 1536

    proto = await any_session.get(ClassPrototype, payload['class_name'])
    assert proto is not None
    assert proto.n_docs == data['n_docs']
    assert len(proto.centroid) == data['centroid_dim']


async def test_predict_by_digest_returns_class(auth_client):
    load_fixtures('classification.sql')
    digest = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='
    class_name = 'annual_report'

    # Seed prototype through recompute endpoint
    recompute_payload = {
        'class_name': class_name,
        'digests': [digest],
        'dry_run': False,
    }
    recompute_response = await auth_client.post('/api/classification/recompute', json=recompute_payload)
    assert recompute_response.status_code == 200

    predict_payload = {
        'mode': 'by_digest',
        'digests': [digest],
        'm_chunk': 8,
        'header_weight_scale': 0.05,
        'document_id': str(uuid4()),
    }
    response = await auth_client.post('/api/classification/predict', json=predict_payload)

    assert response.status_code == 200
    data = response.json()
    assert data['predicted_class'] == class_name
    assert data['abstained'] is False
    assert data['prob'] > 0.5
    assert data['margin'] > 0.0
    assert data['chunks_used'] >= 1


async def test_predict_by_chunks_applies_thresholds(auth_client):
    load_fixtures('classification_api_prototypes.sql')
    payload = {
        'mode': 'by_chunks',
        'chunk_embeddings': [[1.0, 0.0, 0.0]],
        'm_chunk': 1,
        'header_weight_scale': 0.0,
        'thresholds': {
            'min_prob': 0.6,
            'min_margin': 1.1,
        },
        'document_id': str(uuid4()),
    }

    response = await auth_client.post('/api/classification/predict', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['predicted_class'] is None
    assert data['abstained'] is True
    assert data['reason'] == 'below_min_margin'
    assert data['prob'] == pytest.approx(0.731, rel=1e-3)
    assert data['margin'] == pytest.approx(1.0, rel=1e-3)
    assert 'alpha' in data['scores']
    assert 'beta' in data['scores']
