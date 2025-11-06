from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Hashable, Sequence

from .schemas import Candidate, ReduceAggregate


def _normalise_key(value: Any) -> Hashable:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return 'nan'
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_normalise_key(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _normalise_key(v)) for k, v in value.items()))
    return str(value).strip().lower()


@dataclass(slots=True)
class _Group:
    key: Hashable
    raw_value: Any
    candidates: list[Candidate]
    confidence_sum: float = 0.0
    retrieval_sum: float = 0.0

    @property
    def confidence(self) -> float:
        denom = len(self.candidates) or 1
        base = self.confidence_sum / denom if denom else 0.0
        retr = self.retrieval_sum / denom if denom else 0.0
        combined = base * 0.7 + min(max(retr, 0.0), 1.0) * 0.3
        diversity_bonus = min(0.2, 0.05 * max(0, denom - 1))
        return max(0.0, min(combined + diversity_bonus, 1.0))

    @property
    def provenance(self) -> list[str]:
        prov: list[str] = []
        for cand in self.candidates:
            chunk_id = cand.retrieval.chunk_id
            if chunk_id not in prov:
                prov.append(chunk_id)
        return prov


def reduce_candidates(candidates: Sequence[Candidate]) -> ReduceAggregate:
    if not candidates:
        return ReduceAggregate(value=None, confidence=0.0, provenance=(), supporting_candidates=())

    groups: dict[Hashable, _Group] = {}
    for cand in candidates:
        key = _normalise_key(cand.value)
        group = groups.get(key)
        if group is None:
            group = _Group(key=key, raw_value=cand.value, candidates=[])
            groups[key] = group
        group.candidates.append(cand)
        if cand.confidence_local is not None:
            group.confidence_sum += float(cand.confidence_local)
        if cand.retrieval.retr_score is not None:
            group.retrieval_sum += float(cand.retrieval.retr_score)

    best = max(groups.values(), key=lambda g: (len(g.candidates), g.confidence, g.retrieval_sum))
    return ReduceAggregate(
        value=best.raw_value,
        confidence=best.confidence,
        provenance=tuple(best.provenance),
        supporting_candidates=tuple(best.candidates),
    )
