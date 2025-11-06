from __future__ import annotations

import datetime as dt
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from agent.schemas import MetadataSchema
from utils.types import SHA256B64


class ManualMetadataUpdateDTO(BaseModel):
    metadata: MetadataSchema = Field(..., description='Manually supplied metadata payload.')


class MetadataVersionResponse(BaseModel):
    document_id: UUID
    version: int
    fingerprint: str
    extracted_on: dt.datetime
    metadata: MetadataSchema


class DocumentSearchResponse(BaseModel):
    document_ids: list[UUID]
    digests: list[SHA256B64 | None]

    @model_validator(mode='after')
    def _validate_lengths(self) -> 'DocumentSearchResponse':
        if len(self.document_ids) != len(self.digests):
            raise ValueError('document_ids and digests must have the same length')
        return self


VersionQuery = Annotated[
    str | None,
    StringConstraints(pattern=r'^(latest|v\d+)?$', max_length=16),
]
