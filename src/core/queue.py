from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from loguru import logger

from core import get_settings

settings = get_settings()


def setup_broker() -> None:
    """Configure Dramatiq broker from environment."""
    if dramatiq.get_broker() is not None:
        return

    url = settings.redis_url.get_secret_value()
    broker = RedisBroker(url=url)

    dramatiq.set_broker(broker)
    logger.info('Dramatiq: configured Redis broker', extra={'broker_url': url})
