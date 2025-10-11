from __future__ import annotations

import logging
from typing import Dict

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_tracing_configured = False
_metrics_configured = False


def parse_otlp_headers(raw_headers: str | None) -> Dict[str, str]:
    if not raw_headers:
        return {}
    headers: Dict[str, str] = {}
    for pair in raw_headers.split(','):
        item = pair.strip()
        if not item or '=' not in item:
            continue
        key, value = item.split('=', 1)
        headers[key.strip()] = value.strip()
    return headers


def build_resource(settings: Settings):
    try:
        from opentelemetry.sdk.resources import Resource
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError('OpenTelemetry SDK not available for resource creation.') from exc

    return Resource.create(
        {
            'service.name': settings.app_name,
            'service.version': settings.version,
            'deployment.environment': settings.env,
        }
    )


def _configure_tracing(settings: Settings, resource) -> None:
    global _tracing_configured
    if _tracing_configured or not settings.otlp_endpoint or not settings.otel_traces_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # pragma: no cover - missing optional dependency
        logger.warning('OpenTelemetry tracing disabled: otlp exporter not available.')
        return

    headers = parse_otlp_headers(settings.otlp_headers)
    exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, headers=headers)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _tracing_configured = True


def _configure_metrics(settings: Settings, resource) -> None:
    global _metrics_configured
    if _metrics_configured or not settings.otlp_endpoint or not settings.otel_metrics_enabled:
        return

    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    except ImportError:  # pragma: no cover - missing optional dependency
        logger.warning('OpenTelemetry metrics disabled: otlp exporter not available.')
        return

    headers = parse_otlp_headers(settings.otlp_headers)
    exporter = OTLPMetricExporter(endpoint=settings.otlp_endpoint, headers=headers)
    reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    _metrics_configured = True


def init_observability() -> None:
    """Configure tracing and metrics providers using OTLP exporters."""
    settings = get_settings()
    try:
        resource = build_resource(settings)
    except RuntimeError:
        logger.warning('OpenTelemetry SDK not installed; observability exporters skipped.')
        return

    _configure_tracing(settings, resource)
    _configure_metrics(settings, resource)


__all__ = ['init_observability', 'build_resource', 'parse_otlp_headers']
