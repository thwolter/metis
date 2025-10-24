import os

import pytest
from dotenv import load_dotenv

from core.config import get_settings

# Provide default test-friendly configuration values.
os.environ.setdefault('POSTGRES_URL', 'sqlite:///:memory:')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('OPENAI_API_KEY', 'test-key')
os.environ.setdefault('TAVILY_API_KEY', 'test-key')
os.environ.setdefault('INTERNAL_AUTH_TOKEN', 'test-token')


@pytest.fixture(scope='session')
def anyio_backend():
    return 'asyncio'


def pytest_collection_modifyitems(config, items):
    # Skip tests that require LangSmith if no API key is configured
    if not os.environ.get('LANGSMITH_API_KEY'):
        skip_langsmith = pytest.mark.skip(reason='LANGSMITH_API_KEY not set; skipping LangSmith-marked tests')
        for item in items:
            if 'langsmith' in item.keywords:
                item.add_marker(skip_langsmith)


@pytest.fixture()
def refresh_settings():
    def _refresh(*, reload_dotenv: bool = False, dotenv_path: str | None = None):
        if reload_dotenv:
            load_dotenv(dotenv_path, override=True)
        get_settings.cache_clear()
        settings = get_settings()
        # Ensure the Dramatiq broker picks up the refreshed settings (e.g. Redis credentials).
        from core.queueing import setup_broker

        setup_broker()
        return settings

    return _refresh
