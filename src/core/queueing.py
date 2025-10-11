from __future__ import annotations

import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from core import configure_logging, get_settings

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


def _make_broker() -> RedisBroker:
    """Construct a Redis broker from settings. Fail fast if missing."""
    url = settings.redis_url.get_secret_value()
    if not url:
        raise RuntimeError('REDIS_URL/redis_url is not configured')
    return RedisBroker(url=url)


# Expose a module-level broker so the CLI can import it via `queue:broker`.
broker: RedisBroker = _make_broker()


def setup_broker() -> None:
    """Configure Dramatiq to use our broker when invoked via `queue:setup_broker`."""
    if dramatiq.get_broker() is not None:
        return
    dramatiq.set_broker(broker)
    broker_url = broker.url if hasattr(broker, 'url') else '<hidden>'
    logger.info('Dramatiq Redis broker configured | url=%s', broker_url)
