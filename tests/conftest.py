import os

import pytest


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
