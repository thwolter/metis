from __future__ import annotations

import uuid

import pytest
from sqlmodel import select

from classification.models import (
    ClassificationRun,
    ClassPrototype,
    DocClass,
    HeaderWeight,
)
from metadata.models import Document
from tests.db import reset_database_state  # type: ignore[import]


@pytest.fixture(scope='module', autouse=True)
async def reset_db():
    await reset_database_state()


async def test_cascade_docclass_children(auth_session):
    await reset_database_state()
    c = DocClass(class_name='annual_report', enabled=True)
    auth_session.add(c)
    await auth_session.flush()

    p = ClassPrototype(
        class_name='annual_report',
        centroid=[0.1, 0.2, 0.3],
        dispersion=0.12,
        n_docs=3,
    )
    h = HeaderWeight(
        class_name='annual_report',
        pattern="auditor's report",
        is_regex=False,
        weight=1.8,
    )
    auth_session.add_all([p, h])
    await auth_session.commit()

    assert (await auth_session.get(DocClass, 'annual_report')) is not None
    assert (await auth_session.get(ClassPrototype, 'annual_report')) is not None
    assert (await auth_session.exec(select(HeaderWeight).where(HeaderWeight.class_name == 'annual_report'))) is not None

    await auth_session.delete(c)
    await auth_session.commit()

    assert (await auth_session.get(DocClass, 'annual_report')) is None
    assert (await auth_session.get(ClassPrototype, 'annual_report')) is None
    assert (
        await auth_session.exec(select(HeaderWeight).where(HeaderWeight.class_name == 'annual_report'))
    ).first() is None


async def test_cascade_document_runs(auth_session):
    tenant_id = auth_session.info['tenant_id']
    user_id = auth_session.info['user_id']
    document_id = uuid.uuid4()

    # prerequisite class
    cls = DocClass(class_name='company_register', enabled=True)
    auth_session.add(cls)
    await auth_session.flush()

    # create a document
    doc = Document(tenant_id=tenant_id, document_id=document_id, created_by=user_id)
    auth_session.add(doc)
    await auth_session.flush()

    run = ClassificationRun(
        tenant_id=tenant_id,
        document_id=document_id,
        predicted_class='company_register',
        prob=0.91,
        margin=0.24,
        chunks_used=7,
        config={'tau_margin': 0.2, 'tau_prob': 0.8},
    )
    auth_session.add(run)
    await auth_session.commit()

    rows = (
        await auth_session.execute(
            select(ClassificationRun).where(
                ClassificationRun.tenant_id == tenant_id,
                ClassificationRun.document_id == document_id,
            )
        )
    ).all()
    assert len(rows) == 1

    # delete document, expect cascade
    await auth_session.delete(doc)
    await auth_session.commit()

    rows = (
        await auth_session.execute(
            select(ClassificationRun).where(
                ClassificationRun.tenant_id == tenant_id,
                ClassificationRun.document_id == document_id,
            )
        )
    ).all()
    assert len(rows) == 0
