import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from dotenv import load_dotenv

from core.config import get_settings

# Load session-level fixtures (auth, client, data) for all tests
pytest_plugins = []

if TYPE_CHECKING:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = Path(__file__).resolve().parent


DEFAULT_ENV_VARS = {
    'OPENAI_API_KEY': 'test-key',
    'TAVILY_API_KEY': 'test-key',
    'JWT_SECRET': 'test-secret',
    'ENV': 'testing',
    'DOCUMENT_STORE': 'local',
}


def pytest_collection_modifyitems(config, items):
    # Skip tests that require LangSmith if no API key is configured
    if not os.environ.get('LANGSMITH_API_KEY'):
        skip_langsmith = pytest.mark.skip(reason='LANGSMITH_API_KEY not set; skipping LangSmith-marked tests')
        for item in items:
            if 'langsmith' in item.keywords:
                item.add_marker(skip_langsmith)


def pytest_runtest_setup(item: pytest.Item):
    def _missing(vars_: list[str]) -> list[str]:
        return [v for v in vars_ if not os.environ.get(v)]

    if item.get_closest_marker('needs_openai'):
        missing = _missing(['OPENAI_API_KEY'])
        if missing:
            pytest.skip(f'skipped: missing env vars for OpenAI: {", ".join(missing)}')


@pytest.fixture(scope='session', autouse=True)
def _set_default_env() -> None:
    for key, value in DEFAULT_ENV_VARS.items():
        os.environ.setdefault(key, value)


@pytest.fixture()
def refresh_settings():
    def _refresh(*, reload_dotenv: bool = False, dotenv_path: str | None = None):
        if reload_dotenv:
            load_dotenv(dotenv_path, override=True)
        get_settings.cache_clear()
        settings = get_settings()
        # Ensure the Dramatiq broker picks up the refreshed settings (e.g. Redis credentials).
        from core.broker import reset_broker

        reset_broker()
        return settings

    return _refresh
