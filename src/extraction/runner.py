from __future__ import annotations

from typing import Any, Callable

from datasifter import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionRunner,
    JobState,
    RunnerDefaults,
)
from datasifter.interfaces import MapEngine, ProgressSink
from sqlmodel.ext.asyncio.session import AsyncSession

from core import get_settings

from .adapters import (
    AttributeStore,
    BrokerProgressSink,
    JobRepository,
    RetrievalProvider,
)
from .adapters.map_engine import build_map_engine_factory
from .events import ExtractionEventBroker
from .events import broker as default_broker
from .models import ExtractionJob
from .utils import job_state_from_model


def build_runner(
    session: AsyncSession,
    *,
    broker: ExtractionEventBroker | None = None,
    progress_sink: ProgressSink | None = None,
    job_repository: JobRepository | None = None,
    attribute_store: AttributeStore | None = None,
    retrieval_provider: RetrievalProvider | None = None,
    map_engine_factory: Callable[[str], MapEngine] | None = None,
    defaults: RunnerDefaults | None = None,
) -> ExtractionRunner:
    settings = get_settings()
    sink = progress_sink or BrokerProgressSink(broker or default_broker)

    runner_defaults = defaults or RunnerDefaults(
        model_name=settings.extraction.default_model,
        model_version=settings.extraction.model_version,
        retrieval=settings.extraction.to_retrieval_config(),
    )
    return ExtractionRunner(
        job_repository=job_repository or JobRepository(session),
        attribute_store=attribute_store or AttributeStore(session),
        retrieval_provider=retrieval_provider or RetrievalProvider(session),
        map_engine_factory=map_engine_factory or build_map_engine_factory(),
        defaults=runner_defaults,
        progress_sink=sink,
    )


async def run_extraction(
    session: AsyncSession,
    request: ExtractionRequest,
    *,
    emit: Any | None = None,
    job: ExtractionJob | JobState | None = None,
) -> ExtractionResult:
    del emit  # Progress is published via adapters; emit is kept for compatibility.
    runner = build_runner(session)
    job_state: JobState | None
    if isinstance(job, JobState) or job is None:
        job_state = job
    else:
        job_state = job_state_from_model(job)
    outcome = await runner.run(request, job=job_state)
    return outcome.result
