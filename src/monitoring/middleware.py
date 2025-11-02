"""Dramatiq middleware hooks used for observability in worker processes."""

from __future__ import annotations

from dramatiq.middleware import Middleware


class DramatiqMonitoringMiddleware(Middleware):
    """Placeholder middleware for integrating observability exporters."""

    # The base Middleware class already provides no-op implementations. Explicitly
    # overriding the hooks documents the extension points we rely on when wiring
    # monitoring backends in production deployments.
    def before_process_message(self, broker, message, *, actor=None, options=None) -> None:  # type: ignore[override]
        return None

    def after_process_message(self, broker, message, *, actor=None, options=None, result=None) -> None:  # type: ignore[override]
        return None
