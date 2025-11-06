from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.types import SHA256B64


class AttributeType(str, Enum):
    STRING = 'string'
    INTEGER = 'integer'
    FLOAT = 'float'
    DATE = 'date'
    DATETIME = 'datetime'
    BOOLEAN = 'boolean'
    LIST_STRING = 'list[string]'
    ENUM = 'enum'
    PATTERN = 'pattern'
    JSON = 'json'


class Thresholds(BaseModel):
    model_config = ConfigDict(extra='forbid')

    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    min_chunks: int = Field(default=1, ge=0)


class AttributeConstraints(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enum_values: Sequence[str] | None = Field(default=None, description='Allowed values for enum types.')
    pattern: str | None = Field(default=None, description='Regex pattern the value must match.')
    min_value: float | None = Field(default=None)
    max_value: float | None = Field(default=None)
    normaliser: str | None = Field(default=None, description='Name of the normaliser function to apply.')

    @model_validator(mode='after')
    def _validate_numeric_bounds(self) -> 'AttributeConstraints':
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                msg = 'min_value must be <= max_value'
                raise ValueError(msg)
        return self


class AttributeSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    type: AttributeType
    description: str
    hints: Sequence[str] = Field(default_factory=list)
    regex_hint: str | None = None
    normaliser: str | None = None
    constraints: AttributeConstraints | None = None
    thresholds: Thresholds | None = None


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    max_chunks: int = Field(default=12, ge=1, description='Max number of chunks to retrieve per attribute.')
    top_m: int = Field(default=3, ge=1, description='Top-m informative chunks to keep.')
    header_boost: float = Field(default=0.5, ge=0.0)
    semantic_weight: float = Field(default=1.0, ge=0.0)
    bm25_weight: float = Field(default=0.5, ge=0.0)
    hints_weight: float = Field(default=0.3, ge=0.0)


class RetrievalMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    chunk_id: str
    header: str | None = None
    page: int | None = Field(default=None, ge=0)
    retr_score: float | None = None
    text_excerpt: str | None = None


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra='forbid')

    chunk_id: str
    text: str
    header: str | None = None
    page: int | None = Field(default=None, ge=0)
    retr_score: float | None = None


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attribute: str
    value: Any
    confidence_local: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None
    retrieval: RetrievalMetadata
    raw_json: dict[str, Any] | None = None


class ReduceAggregate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: Sequence[str] = Field(default_factory=tuple)
    supporting_candidates: Sequence[Candidate] = Field(default_factory=tuple)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    code: Literal['enum', 'pattern', 'range', 'normaliser', 'type', 'unknown']
    message: str


class AttributeResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    value: Any | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: Sequence[str] = Field(default_factory=tuple)
    rationale: str | None = None
    validation_issues: Sequence[ValidationIssue] = Field(default_factory=tuple)
    chunk_count: int = Field(default=0, ge=0)
    status: Literal['accepted', 'abstained', 'error'] = 'accepted'


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    doc_id: UUID
    doc_type: str
    tenant_id: UUID | None = None
    digest: SHA256B64 | None = Field(default=None, description='Digest of the document to extract from.')
    collection_name: str | None = Field(default=None, description='Vector store collection name for retrieval.')
    attributes: Sequence[str] | None = Field(default=None, description='Optional subset of attributes to extract.')
    model: str | None = Field(default=None, description='Override the default extraction model.')
    retriever: RetrievalConfig | None = None
    dry_run: bool = False


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_id: UUID
    doc_id: UUID
    doc_type: str
    attributes: dict[str, AttributeResult]
    model: str
    model_version: str
    started_at: datetime
    completed_at: datetime | None
    errors: list[str] = Field(default_factory=list)


class StatusEvent(str, Enum):
    JOB_STARTED = 'job.started'
    JOB_PARTIAL = 'job.partial'
    JOB_COMPLETED = 'job.completed'
    JOB_FAILED = 'job.failed'
    JOB_CANCELED = 'job.canceled'
    ATTRIBUTE_STARTED = 'attribute.started'
    CHUNK_MAPPED = 'chunk.mapped'
    ATTRIBUTE_REDUCED = 'attribute.reduced'
    ATTRIBUTE_VALIDATED = 'attribute.validated'
    ATTRIBUTE_THRESHOLDED = 'attribute.thresholded'
    ATTRIBUTE_PERSISTED = 'attribute.persisted'


class AttributeProgress(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    state: Literal['pending', 'mapping', 'reduced', 'validated', 'thresholded', 'persisted', 'abstained', 'error']
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mapped: int | None = Field(default=None, ge=0)
    planned: int | None = Field(default=None, ge=0)


class ProgressSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attributes_total: int
    attributes_done: int
    map_calls_planned: int
    map_calls_done: int
    reduce_done: int = 0
    validated: int = 0
    persisted: int = 0


class ExtractionStatusPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    seq: int
    timestamp: datetime
    job_id: UUID
    doc_id: UUID
    doc_type: str
    event: StatusEvent
    status: Literal['queued', 'running', 'completed', 'failed']
    progress: ProgressSnapshot | None = None
    attribute: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    summary: str | None = None
    errors: list[str] | None = None
    attributes: Sequence[AttributeProgress] | None = None
    results: dict[str, Any] | None = None

    @field_validator('errors', mode='before')
    @classmethod
    def _normalise_errors(cls, value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return [value]
        return value
