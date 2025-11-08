from __future__ import annotations

from uuid import UUID

import pytest
from sqlmodel import select
from tenauth.schemas import AccessContext

from agent.schemas import MetadataSchema
from metadata.models import Document, DocumentMetadata
from metadata.service import (
    delete_document,
    ensure_document,
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


async def test_ensure_document_idempotent(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=10)

    first = await ensure_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)
    second = await ensure_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)

    assert first.document_id == second.document_id == document_id

    stmt = select(Document)
    documents = (await auth_session.exec(stmt)).all()
    assert len(documents) == 1


async def test_record_metadata_version_handles_custom_fingerprint(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=11)

    record = await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=None,
        fingerprint='custom-fp',
    )

    assert record.version == 1
    assert record.payload == {}
    assert record.fingerprint == 'custom-fp'

    second = await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=_metadata_payload('ACME Beta'),
    )

    assert second.version == 2

    stmt = select(DocumentMetadata).where(
        DocumentMetadata.tenant_id == access.tenant_id,
        DocumentMetadata.document_id == document_id,
    )
    records = (await auth_session.exec(stmt)).all()
    assert len(records) == 2


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


async def test_manual_metadata_update_avoids_duplicate_rows(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=7)
    metadata = _metadata_payload('ACME Duplicate')

    await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )
    await manual_metadata_update(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=metadata,
    )

    stmt = select(DocumentMetadata).where(
        DocumentMetadata.tenant_id == access.tenant_id,
        DocumentMetadata.document_id == document_id,
    )
    records = (await auth_session.exec(stmt)).all()
    assert len(records) == 1


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


async def test_fetch_document_metadata_specific_version(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=8)

    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=_metadata_payload('Version One'),
    )
    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=_metadata_payload('Version Two'),
    )

    record = await fetch_document_metadata(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        version='v1',
    )

    assert record is not None
    assert record.version == 1
    assert record.payload['company_name'] == 'Version One'


async def test_fetch_document_metadata_invalid_version(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=9)

    await record_metadata_version(
        auth_session,
        tenant_id=access.tenant_id,
        document_id=document_id,
        metadata=_metadata_payload('Only Version'),
    )

    with pytest.raises(ValueError):
        await fetch_document_metadata(
            auth_session,
            tenant_id=access.tenant_id,
            document_id=document_id,
            version='first',
        )


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


async def test_delete_document_returns_false_when_missing(auth_session):
    access = AccessContext.from_session(auth_session)
    document_id = UUID(int=12)

    deleted = await delete_document(auth_session, tenant_id=access.tenant_id, document_id=document_id)
    assert deleted is False


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
