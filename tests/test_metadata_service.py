from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine
from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from metadata.models import DocumentMetadata, Job
from metadata.schemas import CreateJobDTO, JobContextPayload
from metadata.service import (
    create_job,
    fetch_document_metadata,
    manual_metadata_update,
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
    original_job_schema = Job.__table__.schema  # type: ignore[missing-attribute]
    original_doc_schema = DocumentMetadata.__table__.schema  # type: ignore[missing-attribute]
    Job.__table__.schema = None  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = None  # type: ignore[missing-attribute]

    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)

    yield engine

    SQLModel.metadata.drop_all(engine)
    Job.__table__.schema = original_job_schema  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = original_doc_schema  # type: ignore[missing-attribute]


@contextmanager
def session_ctx(engine):
    with Session(engine) as session:
        yield session
        session.commit()


def _dto(document_id: UUID | None = None) -> CreateJobDTO:
    context = JobContextPayload(
        digest='A' * 43 + '=',
        collection_name='default',
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


def _access(*, tenant_id: UUID | None = None, user_id: UUID | None = None) -> AccessContext:
    return AccessContext(tenant_id=tenant_id or uuid4(), user_id=user_id or uuid4())


def test_merge_metadata_respects_locked_fields():
    base = MetadataSchema(document_type='Annual Report', company_name='ACME AG', tags=['esg'])
    generated = MetadataSchema(document_type='Other', tags=['finance', 'annual'])

    merged = merge_metadata(base=base, generated=generated, locked_fields=['company_name'])

    assert merged.company_name == 'ACME AG'
    assert merged.document_type == 'Other'
    assert merged.tags == ['finance', 'annual']


def test_create_job_defaults_to_no_locked_fields(engine):
    dto = _dto()
    access = _access()

    with session_ctx(engine) as session:
        job = create_job(session, dto, access_context=access)

    assert job.locked_fields == []


def test_metadata_fingerprint_idempotent():
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME AG')
    fp1 = metadata_fingerprint(metadata)
    fp2 = metadata_fingerprint(metadata)
    assert fp1 == fp2


def test_create_job_is_idempotent(engine):
    dto = _dto()
    access = _access()
    with session_ctx(engine) as session:
        job1 = create_job(session, dto, access_context=access)
        job2 = create_job(session, dto, access_context=access)

    assert job1.job_id == job2.job_id


def test_fetch_document_metadata_latest(engine):
    dto = _dto()
    access = _access()
    with session_ctx(engine) as session:
        job = create_job(session, dto, access_context=access)
        record_metadata_version(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            metadata=dto.metadata,
        )
        session.commit()

        updated = MetadataSchema(document_type='Annual Report', company_name='ACME Group', reporting_year=2024)
        record_metadata_version(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            metadata=updated,
        )
        session.commit()

    with session_ctx(engine) as session:
        record = fetch_document_metadata(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            version='latest',
        )

    assert record is not None
    assert record.version == 2
    assert record.payload['company_name'] == 'ACME Group'


def test_manual_metadata_update_creates_new_version(engine):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = _access()
    with session_ctx(engine) as session:
        job = create_job(session, dto, access_context=access)
        document_id = job.document_id

    with session_ctx(engine) as session:
        record = manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    assert record.version == 1
    assert record.payload['company_name'] == 'ACME AG'


def test_manual_metadata_update_increments_version_on_change(engine):
    dto = _dto()
    base_metadata = dto.metadata
    assert base_metadata is not None
    access = _access()
    with session_ctx(engine) as session:
        job = create_job(session, dto, access_context=access)
        document_id = job.document_id

    with session_ctx(engine) as session:
        first = manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=base_metadata,
        )

    updated = base_metadata.model_copy(update={'company_name': 'ACME Group', 'reporting_year': 2024})

    with session_ctx(engine) as session:
        second = manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=updated,
        )

    assert first.version == 1
    assert second.version == 2
    assert second.payload['company_name'] == 'ACME Group'
    assert second.payload['reporting_year'] == 2024


def test_manual_metadata_update_skips_duplicate_payload(engine):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = _access()
    with session_ctx(engine) as session:
        job = create_job(session, dto, access_context=access)
        document_id = job.document_id

    with session_ctx(engine) as session:
        first = manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    with session_ctx(engine) as session:
        second = manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    assert first.version == second.version == 1
