from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from loguru import logger

from core import get_settings

settings = get_settings()


def _make_broker() -> RedisBroker:
    """Construct a Redis broker from settings. Fail fast if missing."""
    url = settings.redis_url.get_secret_value()
    if not url:
        raise RuntimeError("REDIS_URL/redis_url is not configured")
    return RedisBroker(url=url)


# Expose a module-level broker so the CLI can import it via `queue:broker`.
broker: RedisBroker = _make_broker()


def setup_broker() -> None:
    """Configure Dramatiq to use our broker when invoked via `queue:setup_broker`."""
    if dramatiq.get_broker() is not None:
        return
    dramatiq.set_broker(broker)
    logger.info("Dramatiq: configured Redis broker | url={}", broker.url if hasattr(broker, "url") else "<hidden>")
