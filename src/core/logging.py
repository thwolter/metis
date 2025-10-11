from __future__ import annotations

import logging

from core.config import Settings, get_settings
from core.observability import build_resource, parse_otlp_headers

_configured = False


def _configure_otel_logging(settings: Settings, *, level: int, root_logger: logging.Logger) -> None:
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    except ImportError:  # pragma: no cover - optional dependency
        root_logger.warning('OpenTelemetry log exporter not available; skipping OTLP log forwarding.')
        return
    try:
        from opentelemetry.sdk._logs import (  # type: ignore[attr-defined]
            LoggerProvider,
            LoggingHandler,
        )
        from opentelemetry.sdk._logs.export import (
            BatchLogRecordProcessor,  # type: ignore[attr-defined]
        )
    except ImportError:  # pragma: no cover - optional dependency
        root_logger.warning('OpenTelemetry logging SDK modules not available; skipping OTLP log forwarding.')
        return

    try:
        resource = build_resource(settings)
    except RuntimeError:
        root_logger.warning('OpenTelemetry SDK not available; skipping OTLP log forwarding.')
        return

    exporter = OTLPLogExporter(
        endpoint=settings.otlp_endpoint,
        headers=parse_otlp_headers(settings.otlp_headers),
    )
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    otel_handler = LoggingHandler(level=level, logger_provider=provider)
    otel_handler.setLevel(level)
    root_logger.addHandler(otel_handler)


def configure_logging() -> None:
    """Initialise stdlib logging and optionally bridge to OpenTelemetry."""
    global _configured
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

    if settings.otel_logs_enabled and settings.otlp_endpoint:
        _configure_otel_logging(settings, level=level, root_logger=root_logger)

    _configured = True


__all__ = ['configure_logging']
