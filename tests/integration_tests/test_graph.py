from uuid import UUID

import pytest

from agent import graph
from agent.schemas import ContextSchema

pytestmark = pytest.mark.anyio


@pytest.mark.langsmith
async def test_agent_simple_passthrough() -> None:
    context = ContextSchema(
        digest='vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc=',
        collection_name='default',
        tenant_id=UUID('ae579baf-91c2-4497-abf5-44867e06c7a1'),
    )
    res = await graph.ainvoke({}, config={'configurable': context.model_dump()})
    assert res is not None
