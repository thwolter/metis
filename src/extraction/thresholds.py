from __future__ import annotations

from typing import Sequence

from .schemas import AttributeResult, Candidate, Thresholds


def passes_thresholds(result: AttributeResult, thresholds: Thresholds, chunk_count: int) -> bool:
    if thresholds.min_confidence is not None:
        if result.confidence is None or result.confidence < thresholds.min_confidence:
            return False
    if thresholds.min_chunks is not None and chunk_count < thresholds.min_chunks:
        return False
    return True


def abstain_output(attribute: str, candidates: Sequence[Candidate]) -> AttributeResult:
    provenance = [cand.retrieval.chunk_id for cand in candidates if cand.retrieval]
    return AttributeResult(
        name=attribute,
        value=None,
        confidence=None,
        provenance=tuple(provenance),
        rationale='Confidence or evidence below threshold; abstaining',
        status='abstained',
        chunk_count=len(candidates),
    )
