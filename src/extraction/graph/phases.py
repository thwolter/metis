from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..persistence import persist_attribute
from ..reduce_step import reduce_candidates
from ..retrieval import retrieve_chunks
from ..schemas import (
    AttributeResult,
    AttributeSpec,
    Candidate,
    RetrievedChunk,
    StatusEvent,
    Thresholds,
)
from ..thresholds import abstain_output, passes_thresholds
from ..validate import apply_validation
from .context import ExtractionContext
from .progress import AttributeState


def _default_thresholds() -> Thresholds:
    return Thresholds(min_confidence=0.65, min_chunks=1)


async def retrieve_attribute_chunks(
    context: ExtractionContext,
    spec: AttributeSpec,
    attr_state: AttributeState,
) -> list[RetrievedChunk]:
    chunks = await retrieve_chunks(
        context.session,
        tenant_id=context.job.tenant_id,
        collection_name=context.collection_name,
        digest=context.digest,
        doc_type=context.request.doc_type,
        attribute=spec,
        config=context.retrieval_config,
    )

    if context.retrieval_config.top_m and context.retrieval_config.top_m < len(chunks):
        map_chunks = list(chunks[: context.retrieval_config.top_m])
    else:
        map_chunks = list(chunks)

    attr_state.planned = len(map_chunks)
    context.progress.map_calls_planned += len(map_chunks)
    return map_chunks


async def map_attribute_chunks(
    context: ExtractionContext,
    spec: AttributeSpec,
    map_chunks: Sequence[RetrievedChunk],
    attr_state: AttributeState,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for chunk in map_chunks:
        await context.ensure_active()
        candidate = await context.map_extractor.extract_candidate(
            doc_type=context.request.doc_type,
            attribute=spec,
            chunk=chunk,
            attempt=len(candidates) + 1,
        )
        candidates.append(candidate)
        attr_state.mapped += 1
        context.progress.map_calls_done += 1
        await context.emitter.emit(
            StatusEvent.CHUNK_MAPPED,
            attribute_payload={
                'name': spec.name,
                'phase': 'map',
                'retrieval': candidate.retrieval.model_dump(mode='json'),
                'candidate': {
                    'value': candidate.value,
                    'confidence_local': candidate.confidence_local,
                    'rationale': candidate.rationale,
                },
            },
        )
    return candidates


async def reduce_attribute(
    context: ExtractionContext,
    spec: AttributeSpec,
    candidates: Sequence[Candidate],
    attr_state: AttributeState,
) -> Any:
    aggregate = reduce_candidates(candidates)
    context.progress.reduce_done += 1
    attr_state.state = 'reduced'
    attr_state.confidence = aggregate.confidence
    await context.ensure_active()
    await context.emitter.emit(
        StatusEvent.ATTRIBUTE_REDUCED,
        attribute_payload={
            'name': spec.name,
            'phase': 'reduce',
            'aggregate': {
                'value': aggregate.value,
                'confidence': aggregate.confidence,
                'provenance': list(aggregate.provenance),
                'supporting': [cand.raw_json for cand in aggregate.supporting_candidates],
            },
        },
    )
    return aggregate


async def validate_attribute(
    context: ExtractionContext,
    spec: AttributeSpec,
    aggregate: Any,
    chunk_count: int,
    attr_state: AttributeState,
) -> AttributeResult:
    validated = apply_validation(
        attribute=spec,
        value=aggregate.value,
        confidence=aggregate.confidence,
        chunk_count=chunk_count,
        provenance=aggregate.provenance,
    )
    context.progress.validated += 1
    attr_state.state = 'validated'
    attr_state.confidence = validated.confidence

    await context.ensure_active()
    await context.emitter.emit(
        StatusEvent.ATTRIBUTE_VALIDATED,
        attribute_payload={
            'name': spec.name,
            'phase': 'validate',
            'value': validated.value,
            'issues': [issue.model_dump() for issue in validated.validation_issues],
        },
    )
    return validated


async def threshold_and_persist(
    context: ExtractionContext,
    spec: AttributeSpec,
    validated: AttributeResult,
    candidates: Sequence[Candidate],
    chunk_count: int,
    attr_state: AttributeState,
) -> AttributeResult:
    thresholds = spec.thresholds or _default_thresholds()
    passes = passes_thresholds(validated, thresholds, chunk_count)
    attr_state.state = 'thresholded'
    decision = 'accept' if passes else 'abstain'
    await context.ensure_active()
    await context.emitter.emit(
        StatusEvent.ATTRIBUTE_THRESHOLDED,
        attribute_payload={
            'name': spec.name,
            'phase': 'threshold',
            'decision': decision,
            'thresholds': thresholds.model_dump(),
        },
    )

    if not passes or context.request.dry_run:
        result = abstain_output(spec.name, candidates)
        attr_state.state = 'abstained' if not passes else 'persisted'
        context.progress.attributes_done += 1
        await context.ensure_active()
        await context.emitter.emit(
            StatusEvent.ATTRIBUTE_PERSISTED,
            attribute_payload={
                'name': spec.name,
                'phase': 'persist',
                'value': result.value,
                'confidence': result.confidence,
                'status': result.status,
            },
            include_snapshot=True,
        )
        return result

    record = await persist_attribute(
        context.session,
        tenant_id=context.job.tenant_id,
        job=context.job,
        result=validated,
        spec=spec,
    )
    context.progress.persisted += 1
    context.progress.attributes_done += 1
    attr_state.state = 'persisted'
    attr_state.confidence = validated.confidence
    await context.ensure_active()
    await context.emitter.emit(
        StatusEvent.ATTRIBUTE_PERSISTED,
        attribute_payload={
            'name': spec.name,
            'phase': 'persist',
            'value': record.value_json,
            'confidence': record.confidence,
            'status': validated.status,
        },
        include_snapshot=True,
    )
    return validated


__all__ = [
    'retrieve_attribute_chunks',
    'map_attribute_chunks',
    'reduce_attribute',
    'validate_attribute',
    'threshold_and_persist',
]
