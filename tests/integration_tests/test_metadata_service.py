from __future__ import annotations

from uuid import UUID

from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from metadata.schemas import CreateJobDTO, JobContextPayload
from metadata.service import (
    create_job,
    delete_document,
    fetch_document_metadata,
    get_job,
    manual_metadata_update,
    merge_metadata,
    metadata_fingerprint,
    record_metadata_version,
)


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


def test_merge_metadata_respects_locked_fields():
    base = MetadataSchema(document_type='Annual Report', company_name='ACME AG', tags=['esg'])
    generated = MetadataSchema(document_type='Other', tags=['finance', 'annual'])

    merged = merge_metadata(base=base, generated=generated, locked_fields=['company_name'])

    assert merged.company_name == 'ACME AG'
    assert merged.document_type == 'Other'
    assert merged.tags == ['finance', 'annual']


async def test_create_job_defaults_to_no_locked_fields(auth_session):
    dto = _dto()
    access = AccessContext.from_session(auth_session)

    job = await create_job(auth_session, dto, access_context=access)

    assert job.locked_fields == []
    assert job.collection_name == dto.context.collection_name
    assert job.document_digest == dto.context.digest


def test_metadata_fingerprint_idempotent():
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME AG')
    fp1 = metadata_fingerprint(metadata)
    fp2 = metadata_fingerprint(metadata)
    assert fp1 == fp2


async def test_create_job_is_idempotent(auth_session):
    dto = _dto()
    access = AccessContext.from_session(auth_session)
    job1 = await create_job(auth_session, dto, access_context=access)
    job2 = await create_job(auth_session, dto, access_context=access)

    assert job1.job_id == job2.job_id


async def test_delete_document_removes_jobs_and_metadata(auth_session):
    dto = _dto()
    access = AccessContext.from_session(auth_session)
    document_id = dto.resolved_document_id()

    await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)

    job = await create_job(auth_session, dto, access_context=access)

    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=job.document_id,
        metadata=dto.metadata,
    )

    deleted = await delete_document(auth_session, tenant_id=access.tenant_id, document_id=job.document_id)
    assert deleted is True

    fetched_job = await get_job(auth_session, job.job_id)
    assert fetched_job is None

    record = await fetch_document_metadata(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=job.document_id,
        version='latest',
    )
    assert record is None


async def test_fetch_document_metadata_latest(auth_session):
    dto = _dto()
    access = AccessContext.from_session(auth_session)
    job = await create_job(auth_session, dto, access_context=access)
    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=job.document_id,
        metadata=dto.metadata,
    )

    updated = MetadataSchema(document_type='Annual Report', company_name='ACME Group', reporting_year=2024)
    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=job.document_id,
        metadata=updated,
    )

    record = await fetch_document_metadata(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=job.document_id,
        version='latest',
    )

    assert record is not None
    assert record.version == 2
    assert record.payload['company_name'] == 'ACME Group'


async def test_manual_metadata_update_creates_new_version(auth_session):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = AccessContext.from_session(auth_session)

    document_id = dto.resolved_document_id()
    await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)

    record = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=manual_metadata,
    )

    assert record.version == 1
    assert record.payload['company_name'] == 'ACME AG'


async def test_manual_metadata_update_increments_version_on_change(auth_session):
    dto = _dto()
    base_metadata = dto.metadata
    assert base_metadata is not None
    access = AccessContext.from_session(auth_session)

    document_id = dto.resolved_document_id()
    await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)

    first = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=base_metadata,
    )

    updated = base_metadata.model_copy(update={'company_name': 'ACME Group', 'reporting_year': 2024})

    second = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=updated,
    )

    assert first.version == 1
    assert second.version == 2
    assert second.payload['company_name'] == 'ACME Group'
    assert second.payload['reporting_year'] == 2024


async def test_manual_metadata_update_skips_duplicate_payload(auth_session):
    dto = _dto()
    manual_metadata = dto.metadata
    assert manual_metadata is not None
    access = AccessContext.from_session(auth_session)

    document_id = dto.resolved_document_id()
    await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)

    first = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=manual_metadata,
    )

    second = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=manual_metadata,
    )

    assert first.version == second.version == 1
