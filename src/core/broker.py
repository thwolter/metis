from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from core.config import get_settings
from monitoring.middleware import DramatiqMonitoringMiddleware

logger = __import__('logging').getLogger(__name__)


def _create_broker() -> dramatiq.Broker:
    settings = get_settings()

    if settings.redis_url:
        _broker = RedisBroker(url=settings.redis_url.get_secret_value())
    else:
        _broker = StubBroker()
        logger.warning(
            'Dramatiq broker URL not configured; falling back to in-memory StubBroker. '
            'Tasks will be executed inline during API requests.'
        )

    _broker.add_middleware(DramatiqMonitoringMiddleware())
    return _broker


def _install_broker(_broker: dramatiq.Broker) -> dramatiq.Broker:
    try:
        from dramatiq.middleware.prometheus import (
            Prometheus as _Prometheus,  # type: ignore[import]
        )
    except Exception:  # pragma: no cover - optional dependency
        _Prometheus = None

    if _Prometheus is not None:
        for middleware in list(_broker.middleware):
            if isinstance(middleware, _Prometheus):
                _broker.middleware.remove(middleware)

    dramatiq.set_broker(_broker)
    return _broker


def _init_broker() -> dramatiq.Broker:
    return _install_broker(_create_broker())


broker = _init_broker()


def reset_broker() -> dramatiq.Broker:
    """Rebuild and install a fresh Dramatiq broker using the current settings.

    Useful in integration tests which mutate environment variables at runtime.
    """

    global broker
    broker = _init_broker()
    return broker
