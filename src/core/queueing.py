from __future__ import annotations

import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from core import configure_logging, get_settings

configure_logging()
logger = logging.getLogger(__name__)


def _make_broker() -> RedisBroker:
    """Construct a Redis broker from settings. Fail fast if missing."""
    url = get_settings().redis_url.get_secret_value()
    if not url:
        raise RuntimeError('REDIS_URL/redis_url is not configured')
    return RedisBroker(url=url)


# Expose a module-level broker so the CLI can import it via `queue:broker`.
broker: RedisBroker = _make_broker()


def setup_broker() -> None:
    """Configure Dramatiq to use our broker when invoked via `queue:setup_broker`."""
    global broker

    new_broker = _make_broker()
    current = dramatiq.get_broker()

    def _conn_signature(rb: RedisBroker) -> tuple:
        pool = getattr(rb, 'client', None)
        if pool is None:
            return ()
        connection_pool = getattr(pool, 'connection_pool', None)
        kwargs = getattr(connection_pool, 'connection_kwargs', {}) or {}
        # Normalise to tuple of sorted items so secrets do not leak in logs.
        return tuple(sorted(kwargs.items()))

    new_signature = _conn_signature(new_broker)
    if new_signature:
        redacted = dict(new_signature)
        if 'password' in redacted:
            redacted['password'] = '<redacted>'
        target_desc = f'{redacted}'
    else:
        target_desc = '<unknown>'

    if current is None:
        dramatiq.set_broker(new_broker)
        broker = new_broker
        logger.info('Dramatiq Redis broker configured | settings=%s', target_desc)
        return

    if isinstance(current, RedisBroker) and _conn_signature(current) == new_signature:
        broker = new_broker
        return

    dramatiq.set_broker(new_broker)
    broker = new_broker
    logger.info('Dramatiq Redis broker reconfigured | settings=%s', target_desc)
