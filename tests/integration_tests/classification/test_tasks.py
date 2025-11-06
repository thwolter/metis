from __future__ import annotations

from uuid import UUID

import pytest
from sqlmodel import select

from classification.models import ClassPrototype
from classification.tasks import recompute_class_prototypes
from tests.utils import load_fixtures  # type: ignore[import]


@pytest.fixture(scope='module', autouse=True)
def load_classification_training_data():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')
    load_fixtures('vectra_classifier.sql')
    load_fixtures('classification.sql')
    load_fixtures('classification_labelled_digest.sql')


@pytest.mark.integration
async def test_batch_trainer_recomputes_from_labelled_digests(any_session):
    tenant_id = UUID('f74c8bfb-6372-4f61-b7b7-f4ae7c0abfde')

    result = await recompute_class_prototypes(class_names=['annual_report'], tenant_ids=[tenant_id])

    assert 'annual_report' in result.updated
    assert result.updated['annual_report'] == 1

    stmt = select(ClassPrototype).where(ClassPrototype.class_name == 'annual_report')
    proto = (await any_session.exec(stmt)).first()
    assert proto is not None
    assert proto.n_docs == 1
    assert len(proto.centroid) > 10
