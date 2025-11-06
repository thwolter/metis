from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import JSON, Column, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from core import get_settings
from utils.fields import created_at_field, updated_at_field

APP_SCHEMA = get_settings().metadata_schema


class ExtractionJobStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELED = 'canceled'


class BaseExtractionModel(SQLModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)  # type: ignore[bad-override]


class ExtractionJob(BaseExtractionModel, table=True):
    __tablename__ = 'extraction_jobs'  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint('tenant_id', 'doc_id', 'doc_type', name='uq_extraction_jobs_document'),
        ForeignKeyConstraint(
            ['tenant_id', 'doc_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_extraction_job_document',
            ondelete='CASCADE',
        ),
        {'schema': APP_SCHEMA},
    )

    job_id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID
    doc_id: UUID
    doc_type: str = Field(sa_column=Column(String(128), nullable=False))
    model: str = Field(sa_column=Column(String(128), nullable=False))
    model_version: str = Field(sa_column=Column(String(64), nullable=False))
    status: ExtractionJobStatus = Field(
        default=ExtractionJobStatus.QUEUED,
        sa_column=Column(String(32), nullable=False, server_default=ExtractionJobStatus.QUEUED.value),
    )
    document_digest: str = Field(sa_column=Column(String(128), nullable=False))
    collection_name: str = Field(sa_column=Column(String(255), nullable=False))
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    seq: int = Field(default=0)
    error: str | None = None
    retriever_config: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    options: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    attributes: list['ExtractedAttribute'] = Relationship(
        sa_relationship=relationship(
            'ExtractedAttribute',
            back_populates='job',
            cascade='all, delete-orphan',
            passive_deletes=True,
        )
    )


class ExtractedAttribute(BaseExtractionModel, table=True):
    __tablename__ = 'extracted_attributes'  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint('job_id', 'attribute', name='uq_extracted_attribute_job'),
        {'schema': APP_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID
    job_id: UUID = Field(foreign_key=f'{APP_SCHEMA}.extraction_jobs.job_id', nullable=False)
    doc_id: UUID
    attribute: str = Field(sa_column=Column(String(128), nullable=False))
    value_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    confidence: float | None = None
    provenance: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    model_version: str = Field(sa_column=Column(String(64), nullable=False))
    constraints_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    job: ExtractionJob = Relationship(back_populates='attributes')
