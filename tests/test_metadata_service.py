from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agent.schemas import ContextSchema, MetadataSchema
from metadata.models import DocumentMetadata, Job
from metadata.schemas import CreateJobDTO
from metadata.service import (
    create_job,
    fetch_document_metadata,
    merge_metadata,
    metadata_fingerprint,
    record_metadata_version,
)


@pytest.fixture(autouse=True)
def configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('POSTGRES_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')


@pytest.fixture
def engine():
    original_job_schema = Job.__table__.schema
    original_doc_schema = DocumentMetadata.__table__.schema
    Job.__table__.schema = None
    DocumentMetadata.__table__.schema = None

    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)

    yield engine

    SQLModel.metadata.drop_all(engine)
    Job.__table__.schema = original_job_schema
    DocumentMetadata.__table__.schema = original_doc_schema


@contextmanager
def session_ctx(engine):
    with Session(engine) as session:
        yield session
        session.commit()


def _dto(document_id: UUID | None = None) -> CreateJobDTO:
    context = ContextSchema(
        digest='A' * 43 + '=',
        collection_name='default',
        tenant_id=uuid4(),
    )
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME AG')
    return CreateJobDTO(
        document_id=document_id,
        context=context,
        metadata=metadata,
        profile='default',
        priority=5,
        callback_url=None,
        idempotency_key='test-key',
    )


def test_merge_metadata_respects_locked_fields():
    base = MetadataSchema(document_type='Annual Report', company_name='ACME AG', tags=['esg'])
    generated = MetadataSchema(document_type='Other', tags=['finance', 'annual'])

    merged = merge_metadata(base=base, generated=generated, locked_fields=['company_name'])

    assert merged.company_name == 'ACME AG'
    assert merged.document_type == 'Other'
    assert merged.tags == ['finance', 'annual']


def test_metadata_fingerprint_idempotent():
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME AG')
    fp1 = metadata_fingerprint(metadata)
    fp2 = metadata_fingerprint(metadata)
    assert fp1 == fp2


def test_create_job_is_idempotent(engine):
    dto = _dto()
    with session_ctx(engine) as session:
        job1 = create_job(session, dto)
        job2 = create_job(session, dto)

    assert job1.job_id == job2.job_id


def test_fetch_document_metadata_latest(engine):
    dto = _dto()
    with session_ctx(engine) as session:
        job = create_job(session, dto)
        record_metadata_version(session, document_id=job.document_id, metadata=dto.metadata)
        session.commit()

        updated = MetadataSchema(document_type='Annual Report', company_name='ACME Group', reporting_year=2024)
        record_metadata_version(session, document_id=job.document_id, metadata=updated)
        session.commit()

    with session_ctx(engine) as session:
        record = fetch_document_metadata(session, document_id=job.document_id, version='latest')

    assert record is not None
    assert record.version == 2
    assert record.payload['company_name'] == 'ACME Group'
