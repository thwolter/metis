from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
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
def engine() -> Generator[Engine, None, None]:
    original_job_schema = Job.__table__.schema  # type: ignore[missing-attribute]
    original_doc_schema = DocumentMetadata.__table__.schema  # type: ignore[missing-attribute]
    Job.__table__.schema = None  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = None  # type: ignore[missing-attribute]

    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )

    SQLModel.metadata.create_all(engine)

    yield engine

    SQLModel.metadata.drop_all(engine)
    engine.dispose()
    Job.__table__.schema = original_job_schema  # type: ignore[missing-attribute]
    DocumentMetadata.__table__.schema = original_doc_schema  # type: ignore[missing-attribute]


class AsyncSessionWrapper:
    def __init__(self, session: Session):
        self._session = session

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    async def commit(self):
        return await asyncio.to_thread(self._session.commit)

    async def refresh(self, instance):
        return await asyncio.to_thread(self._session.refresh, instance)

    async def rollback(self):
        return await asyncio.to_thread(self._session.rollback)

    async def close(self):
        return await asyncio.to_thread(self._session.close)

    async def exec(self, statement):
        return await asyncio.to_thread(self._session.exec, statement)

    def expunge(self, instance):
        return self._session.expunge(instance)

    async def get(self, model, ident):
        return await asyncio.to_thread(self._session.get, model, ident)

    async def flush(self):
        return await asyncio.to_thread(self._session.flush)

    @property
    def info(self):
        return self._session.info

    def __getattr__(self, item):
        return getattr(self._session, item)


@asynccontextmanager
async def session_ctx(engine: Engine) -> AsyncIterator[AsyncSession]:
    with Session(engine, expire_on_commit=False) as sync_session:
        session = AsyncSessionWrapper(sync_session)
        exc: Exception | None = None
        try:
            yield cast(AsyncSession, session)
        except Exception as err:
            exc = err
            await session.rollback()
            raise
        finally:
            if exc is None:
                await session.commit()


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


@pytest.mark.asyncio
async def test_create_job_defaults_to_no_locked_fields(engine: Engine):
    dto = _dto()
    access = _access()

    async with session_ctx(engine) as session:
        job = await create_job(session, dto, access_context=access)

    assert job.locked_fields == []
    assert job.collection_name == dto.context.collection_name
    assert job.document_digest == dto.context.digest


def test_metadata_fingerprint_idempotent():
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME AG')
    fp1 = metadata_fingerprint(metadata)
    fp2 = metadata_fingerprint(metadata)
    assert fp1 == fp2


@pytest.mark.asyncio
async def test_create_job_is_idempotent(engine: Engine):
    dto = _dto()
    access = _access()
    async with session_ctx(engine) as session:
        job1 = await create_job(session, dto, access_context=access)
        job2 = await create_job(session, dto, access_context=access)

    assert job1.job_id == job2.job_id


@pytest.mark.asyncio
async def test_fetch_document_metadata_latest(engine: Engine):
    dto = _dto()
    access = _access()
    async with session_ctx(engine) as session:
        job = await create_job(session, dto, access_context=access)
        await record_metadata_version(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            metadata=dto.metadata,
        )

        updated = MetadataSchema(document_type='Annual Report', company_name='ACME Group', reporting_year=2024)
        await record_metadata_version(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            metadata=updated,
        )

    async with session_ctx(engine) as session:
        record = await fetch_document_metadata(
            session,
            tenant_id=access.tenant_id,
            document_id=job.document_id,
            version='latest',
        )

    assert record is not None
    assert record.version == 2
    assert record.payload['company_name'] == 'ACME Group'


@pytest.mark.asyncio
async def test_manual_metadata_update_creates_new_version(engine: Engine):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = _access()
    async with session_ctx(engine) as session:
        job = await create_job(session, dto, access_context=access)
        document_id = job.document_id

    async with session_ctx(engine) as session:
        record = await manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    assert record.version == 1
    assert record.payload['company_name'] == 'ACME AG'


@pytest.mark.asyncio
async def test_manual_metadata_update_increments_version_on_change(engine: Engine):
    dto = _dto()
    base_metadata = dto.metadata
    assert base_metadata is not None
    access = _access()
    async with session_ctx(engine) as session:
        job = await create_job(session, dto, access_context=access)
        document_id = job.document_id

    async with session_ctx(engine) as session:
        first = await manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=base_metadata,
        )

    updated = base_metadata.model_copy(update={'company_name': 'ACME Group', 'reporting_year': 2024})

    async with session_ctx(engine) as session:
        second = await manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=updated,
        )

    assert first.version == 1
    assert second.version == 2
    assert second.payload['company_name'] == 'ACME Group'
    assert second.payload['reporting_year'] == 2024


@pytest.mark.asyncio
async def test_manual_metadata_update_skips_duplicate_payload(engine: Engine):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = _access()
    async with session_ctx(engine) as session:
        job = await create_job(session, dto, access_context=access)
        document_id = job.document_id

    async with session_ctx(engine) as session:
        first = await manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    async with session_ctx(engine) as session:
        second = await manual_metadata_update(
            session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            metadata=manual_metadata,
        )

    assert first.version == second.version == 1
