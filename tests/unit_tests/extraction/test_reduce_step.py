from __future__ import annotations

from extraction.reduce_step import reduce_candidates
from extraction.schemas import Candidate, RetrievalMetadata


def make_candidate(value, confidence, chunk_id, retr_score) -> Candidate:
    return Candidate(
        attribute='company_name',
        value=value,
        confidence_local=confidence,
        rationale='',
        retrieval=RetrievalMetadata(
            chunk_id=chunk_id,
            header=None,
            page=None,
            retr_score=retr_score,
        ),
    )


def test_reduce_candidates_prefers_majority_vote() -> None:
    candidates = [
        make_candidate('Example Corp', 0.8, 'chunk-1', 0.9),
        make_candidate('Example Corp', 0.6, 'chunk-2', 0.8),
        make_candidate('Another Corp', 0.9, 'chunk-3', 0.5),
    ]
    aggregate = reduce_candidates(candidates)
    assert aggregate.value == 'Example Corp'
    assert aggregate.confidence >= 0.6
    assert set(aggregate.provenance) == {'chunk-1', 'chunk-2'}
