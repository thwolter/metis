from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import JSON, Column, ForeignKeyConstraint, Index
from sqlalchemy.orm import Mapped, relationship
from sqlmodel import Field, Relationship, SQLModel

from core import get_settings
from utils.fields import (
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)

APP_SCHEMA = get_settings().metadata_schema


def utc_now() -> datetime:
    """Return a timezone-naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseSQLModel(SQLModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)  # type: ignore[bad-override]


class Document(BaseSQLModel, table=True):
    """Logical container for document-scoped metadata."""

    __tablename__ = 'documents'  # type: ignore[bad-argument-type]
    __table_args__ = ({'schema': APP_SCHEMA},)

    tenant_id: UUID = Field(primary_key=True)
    document_id: UUID = Field(primary_key=True)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    created_by: UUID = created_by_field()
    updated_by: UUID | None = updated_by_field()

    metadata_versions: Mapped[list['DocumentMetadata']] = Relationship(
        sa_relationship=relationship(
            'DocumentMetadata',
            back_populates='document',
            cascade='all, delete-orphan',
            passive_deletes=True,
        )
    )


class DocumentMetadata(BaseSQLModel, table=True):
    """Versioned metadata payload maintained manually or by extraction."""

    __tablename__ = 'document_metadata'  # type: ignore[bad-argument-type]
    __table_args__ = (
        Index('ix_docmeta_tenant_doc_version', 'tenant_id', 'document_id', 'version', unique=True),
        ForeignKeyConstraint(
            ['tenant_id', 'document_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_document_metadata_document',
            ondelete='CASCADE',
        ),
        {'schema': APP_SCHEMA},
    )

    tenant_id: UUID = Field(primary_key=True)
    document_id: UUID = Field(primary_key=True)
    version: int = Field(primary_key=True)
    fingerprint: str
    extracted_on: datetime = Field(default_factory=utc_now)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    created_by: UUID = created_by_field()
    updated_by: UUID | None = updated_by_field()
    payload: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description='Full metadata payload as JSON.',
    )

    document: Mapped['Document'] = Relationship(
        sa_relationship=relationship('Document', back_populates='metadata_versions')
    )
