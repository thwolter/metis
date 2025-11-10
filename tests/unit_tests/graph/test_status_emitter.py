from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from extraction.graph.progress import AttributeState, ProgressTracker
from extraction.graph.status import StatusEmitter
from extraction.models import ExtractionJob, ExtractionJobStatus
from extraction.schemas import ExtractionStatusPayload, StatusEvent


async def test_status_emitter_triggers_callback_with_correct_payload():
    mock_session = AsyncMock()
    mock_session.add = Mock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.in_transaction = Mock(return_value=True)
    mock_job = ExtractionJob(
        job_id=uuid4(),
        tenant_id=uuid4(),
        doc_id=uuid4(),
        doc_type='report',
        model='test_model',
        model_version='1.0',
        status=ExtractionJobStatus.RUNNING,
        document_digest='digest',
        collection_name='collection',
    )
    mock_progress = ProgressTracker(total_attributes=1)
    mock_attribute_states = {'attr1': AttributeState(name='attr1')}

    callback = AsyncMock()
    status_emitter = StatusEmitter(
        session=mock_session,
        job=mock_job,
        doc_id=mock_job.doc_id,
        doc_type=mock_job.doc_type,
        callback=callback,
        progress=mock_progress,
        attribute_states=mock_attribute_states,
    )

    event = StatusEvent.JOB_STARTED
    payload = await status_emitter.emit(event, include_snapshot=True)

    callback.assert_called_once()
    mock_session.commit.assert_awaited_once()
    assert isinstance(payload, ExtractionStatusPayload)
    assert payload.event == event
    assert payload.job_id == mock_job.job_id
    assert payload.doc_id == mock_job.doc_id
    assert payload.status == mock_job.status
