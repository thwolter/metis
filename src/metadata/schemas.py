from __future__ import annotations

import datetime as dt
from typing import Annotated
from uuid import UUID, uuid5

from pydantic import AnyHttpUrl, BaseModel, Field, StringConstraints, conint

from agent.schemas import ContextSchema, MetadataSchema
from metadata.models import JobStatus

METADATA_DOCUMENT_NAMESPACE = UUID('6e14968a-5b92-4774-a1f0-655f4eca8ef8')


class CreateJobDTO(BaseModel):
    document_id: UUID | None = Field(
        default=None,
        description='Document identifier. When omitted, a deterministic UUID is derived from the digest.',
    )
    context: ContextSchema
    metadata: MetadataSchema | None = Field(
        default=None,
        description='Optional pre-filled metadata. Agent output may overwrite fields unless they are locked.',
    )
    locked_fields: list[str] | None = Field(
        default=None,
        description='Explicit list of metadata fields that must not be overwritten; omit or pass [] to allow updates.',
    )
    profile: str = Field(default='default', description='Processing profile (selects agent strategy).')
    priority: conint(ge=0, le=10) | None = Field(
        default=5, description='Processing priority (lower value → higher priority).'
    )
    callback_url: AnyHttpUrl | None = Field(
        default=None,
        description='Optional callback URL invoked after successful metadata extraction.',
    )
    idempotency_key: str | None = Field(
        default=None,
        description='Optional idempotency key to avoid reprocessing identical requests.',
        json_schema_extra={'maxLength': 128},
    )

    def resolved_document_id(self) -> UUID:
        if self.document_id is not None:
            return self.document_id
        return uuid5(METADATA_DOCUMENT_NAMESPACE, self.context.digest)


class RebuildJobDTO(CreateJobDTO):
    pass


class ManualMetadataUpdateDTO(BaseModel):
    metadata: MetadataSchema


class JobCreatedResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    status_url: str
    result_url: str | None = None


class JobStatusResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    tenant_id: UUID
    status: JobStatus
    retries: int
    priority: int
    created_at: dt.datetime
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    error_type: str | None = None
    error_msg: str | None = None
    result_url: str | None = None


class MetadataVersionResponse(BaseModel):
    document_id: UUID
    version: int
    fingerprint: str
    extracted_on: dt.datetime
    metadata: MetadataSchema


class JobCancelResponse(BaseModel):
    job_id: UUID
    status: JobStatus


VersionQuery = Annotated[
    str | None,
    StringConstraints(pattern=r'^(latest|v\d+)?$', max_length=16),
]
