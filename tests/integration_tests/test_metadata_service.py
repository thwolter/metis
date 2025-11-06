from __future__ import annotations

from uuid import UUID

from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from metadata.service import (
    delete_document,
    fetch_document_metadata,
    manual_metadata_update,
    metadata_fingerprint,
    record_metadata_version,
    search_documents,
)


def _metadata_payload(company_name: str) -> MetadataSchema:
    return MetadataSchema(document_type='Annual Report', company_name=company_name)


async def test_metadata_fingerprint_idempotent():
    metadata = _metadata_payload('ACME AG')
    fp1 = metadata_fingerprint(metadata)
    fp2 = metadata_fingerprint(metadata)
    assert fp1 == fp2


async def test_manual_metadata_update_creates_versions(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=1)
    metadata = _metadata_payload('ACME AG')

    record = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    assert record.version == 1
    assert record.payload['company_name'] == 'ACME AG'


async def test_manual_metadata_update_skips_duplicate(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=2)
    metadata = _metadata_payload('ACME AG')

    first = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )
    second = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    assert first.version == second.version == 1


async def test_manual_metadata_update_increments_version(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=3)
    metadata = _metadata_payload('ACME AG')
    updated = _metadata_payload('ACME Group')

    first = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )
    second = await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=updated,
    )

    assert first.version == 1
    assert second.version == 2
    assert second.payload['company_name'] == 'ACME Group'


async def test_fetch_document_metadata_latest(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=4)
    metadata = _metadata_payload('ACME AG')

    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    updated = _metadata_payload('ACME Group')
    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=updated,
    )

    record = await fetch_document_metadata(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        version='latest',
    )

    assert record is not None
    assert record.version == 2
    assert record.payload['company_name'] == 'ACME Group'


async def test_delete_document_cascades(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=5)
    metadata = _metadata_payload('ACME AG')

    await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    deleted = await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)
    assert deleted is True

    record = await fetch_document_metadata(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        version='latest',
    )
    assert record is None


async def test_search_documents_matches_fields(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=6)
    metadata = MetadataSchema(document_type='Annual Report', company_name='ACME Holdings', tags=['finance'])
    await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    results = await search_documents(auth_session, tenant_id=access.tenant_id, query='acme')
    assert (document_id, None) in results
