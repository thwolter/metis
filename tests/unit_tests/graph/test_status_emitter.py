from __future__ import annotations

from uuid import uuid4

import pytest
from datasifter.graph.progress import AttributeState, ProgressTracker
from datasifter.graph.status import StatusEmitter
from datasifter.schemas import ExtractionStatusPayload, JobState, JobStatus, StatusEvent


class StubJobRepository:
    def __init__(self) -> None:
        self.seq = 0

    async def prepare_job(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def update_status(self, job, **kwargs):  # pragma: no cover
        return job

    async def refresh(self, job):  # pragma: no cover
        return job

    async def increment_sequence(self, job):
        self.seq += 1
        job.seq = self.seq
        return self.seq


class StubSink:
    def __init__(self) -> None:
        self.payloads: list[ExtractionStatusPayload] = []

    async def publish(self, payload: ExtractionStatusPayload) -> None:
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_status_emitter_publishes_snapshot():
    job = JobState(
        job_id=uuid4(),
        doc_id=uuid4(),
        doc_type='report',
        model='stub-model',
        model_version='1.0',
        status=JobStatus.RUNNING,
    )
    repo = StubJobRepository()
    sink = StubSink()
    progress = ProgressTracker(total_attributes=1)
    attr_states = {'attr1': AttributeState(name='attr1')}

    emitter = StatusEmitter(
        job=job,
        job_repository=repo,
        progress=progress,
        attribute_states=attr_states,
        sink=sink,
    )

    payload = await emitter.emit(StatusEvent.JOB_STARTED, include_snapshot=True)

    assert isinstance(payload, ExtractionStatusPayload)
    assert payload.seq == 1
    assert payload.status == JobStatus.RUNNING
    assert payload.attributes is not None
    assert sink.payloads[0] == payload
