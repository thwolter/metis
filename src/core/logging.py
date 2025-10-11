from __future__ import annotations

import logging
from typing import Dict

from opentelemetry.sdk.resources import Resource

from core.config import get_settings

try:  # OpenTelemetry 1.24+
    from opentelemetry.sdk.logs import LoggerProvider, LoggingHandler  # type: ignore[attr-defined]
    from opentelemetry.sdk.logs.export import BatchLogRecordProcessor  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - fallback for older SDKs
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # type: ignore[attr-defined]
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor  # type: ignore[attr-defined]

try:
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
except ImportError as exc:  # pragma: no cover - dependency misconfiguration
    raise RuntimeError(
        'OpenTelemetry OTLP exporter is missing. Install opentelemetry-exporter-otlp to enable logging.'
    ) from exc

_configured = False
_provider: LoggerProvider | None = None


def _parse_headers(raw_headers: str | None) -> Dict[str, str]:
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


def configure_logging() -> None:
    """Initialise stdlib logging with optional OpenTelemetry export."""
    global _configured, _provider
    if _configured:
        return

    settings = get_settings()

    level_name = (settings.log_level or 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        )
    root_logger.setLevel(level)

    resource = Resource.create({'service.name': settings.app_name})
    provider = LoggerProvider(resource=resource)

    if settings.otlp_endpoint:
        exporter = OTLPLogExporter(endpoint=settings.otlp_endpoint, headers=_parse_headers(settings.otlp_headers))
        processor = BatchLogRecordProcessor(exporter)
        provider.add_log_record_processor(processor)
        otel_handler = LoggingHandler(level=level, logger_provider=provider)
        otel_handler.setLevel(level)
        root_logger.addHandler(otel_handler)

    _provider = provider
    _configured = True


__all__ = ['configure_logging']
