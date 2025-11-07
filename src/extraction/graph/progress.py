from __future__ import annotations

from dataclasses import dataclass

from extraction.schemas import AttributeProgress, ProgressSnapshot


@dataclass
class ProgressTracker:
    total_attributes: int
    attributes_done: int = 0
    map_calls_planned: int = 0
    map_calls_done: int = 0
    reduce_done: int = 0
    validated: int = 0
    persisted: int = 0

    def snapshot(self) -> ProgressSnapshot:
        return ProgressSnapshot(
            attributes_total=self.total_attributes,
            attributes_done=self.attributes_done,
            map_calls_planned=self.map_calls_planned,
            map_calls_done=self.map_calls_done,
            reduce_done=self.reduce_done,
            validated=self.validated,
            persisted=self.persisted,
        )


@dataclass
class AttributeState:
    name: str
    state: str = 'pending'
    confidence: float | None = None
    mapped: int = 0
    planned: int = 0

    def to_progress(self) -> AttributeProgress:
        return AttributeProgress(
            name=self.name,
            state=self.state,
            confidence=self.confidence,
            mapped=self.mapped or None,
            planned=self.planned or None,
        )


__all__ = ['ProgressTracker', 'AttributeState']
