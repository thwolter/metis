from __future__ import annotations

from typing import Annotated, List, Literal, Mapping, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# --- Shared ---


class Thresholds(BaseModel):
    min_prob: float = Field(0.0, ge=0.0, le=1.0)
    min_margin: float = Field(0.0, ge=0.0)


# --- Recompute ---


class RecomputeRequest(BaseModel):
    class_name: str = Field(min_length=1)
    digests: Annotated[list[str], Field(min_length=1)]
    dry_run: bool = False


class RecomputeResponse(BaseModel):
    class_name: str
    centroid_dim: int
    n_docs: int
    dispersion: float
    updated: bool
    dry_run: bool


# --- Online update ---


class OnlineUpdateRequest(BaseModel):
    class_name: str = Field(min_length=1)
    digest: str
    ema_alpha: Annotated[float, Field(ge=0.0, le=1.0)] = 0.10
    dry_run: bool = False


class OnlineUpdateResponse(BaseModel):
    class_name: str
    centroid_dim: int
    n_docs: int
    dispersion: float
    updated: bool
    dry_run: bool


# --- Predict ---


class PredictByDigest(BaseModel):
    mode: Literal['by_digest']
    document_id: UUID
    digests: Annotated[list[str], Field(min_length=1)]
    m_chunk: Annotated[int, Field(ge=1)] = 8
    header_weight_scale: Annotated[float, Field(ge=0.0)] = 0.05
    thresholds: Optional[Thresholds] = None


class PredictByChunks(BaseModel):
    mode: Literal['by_chunks']
    document_id: UUID
    chunk_embeddings: Annotated[list[list[float]], Field(min_length=1)]
    chunk_headers: Optional[List[Optional[str]]] = None
    m_chunk: Annotated[int, Field(ge=1)] = 8
    header_weight_scale: Annotated[float, Field(ge=0.0)] = 0.05
    thresholds: Optional[Thresholds] = None


PredictRequest = PredictByDigest | PredictByChunks


class PredictResponse(BaseModel):
    predicted_class: Optional[str]
    prob: float
    margin: float
    chunks_used: int
    scores: Mapping[str, float]
    abstained: bool
    reason: Optional[str] = None
