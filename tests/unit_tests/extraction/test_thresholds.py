from __future__ import annotations

from extraction.schemas import AttributeResult, Candidate, RetrievalMetadata, Thresholds
from extraction.thresholds import abstain_output, passes_thresholds


def make_result(confidence: float | None) -> AttributeResult:
    return AttributeResult(
        name='company_name',
        value='Example Corp',
        confidence=confidence,
        provenance=('chunk-1',),
        chunk_count=2,
    )


def test_passes_thresholds_true() -> None:
    thresholds = Thresholds(min_confidence=0.6, min_chunks=1)
    result = make_result(0.8)
    assert passes_thresholds(result, thresholds, chunk_count=2) is True


def test_passes_thresholds_false_on_confidence() -> None:
    thresholds = Thresholds(min_confidence=0.9, min_chunks=1)
    result = make_result(0.5)
    assert passes_thresholds(result, thresholds, chunk_count=3) is False


def test_passes_thresholds_false_on_chunk_count() -> None:
    thresholds = Thresholds(min_confidence=0.6, min_chunks=3)
    result = make_result(0.8)
    assert passes_thresholds(result, thresholds, chunk_count=2) is False


def test_abstain_output_preserves_provenance() -> None:
    candidate = Candidate(
        attribute='isin',
        value=None,
        confidence_local=0.1,
        rationale='not found',
        retrieval=RetrievalMetadata(chunk_id='chunk-42', header=None, page=None, retr_score=0.4),
    )
    result = abstain_output('isin', [candidate])
    assert result.status == 'abstained'
    assert result.provenance == ('chunk-42',)
