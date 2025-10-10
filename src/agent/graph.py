from uuid import UUID

from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.nodes import (
    finalize_metadata,
    metadata_cleaner,
    metadata_extractor,
    tools,
    type_extractor,
)
from agent.schemas import ContextSchema, MetadataSchema
from agent.state import State

builder = StateGraph(State, context_schema=ContextSchema, output_schema=MetadataSchema)

builder.add_node('type_extractor', type_extractor)  # pyrefly: ignore[no-matching-overload]
builder.add_node('metadata_extractor', metadata_extractor)  # pyrefly: ignore[no-matching-overload]
builder.add_node('metadata_cleaner', metadata_cleaner)  # pyrefly: ignore[no-matching-overload]
builder.add_node('finalize_metadata', finalize_metadata)  # pyrefly: ignore[no-matching-overload]

builder.add_node('tools_for_type', ToolNode(tools))
builder.add_node('tools_for_metadata', ToolNode(tools))
builder.add_node('tools_for_cleaner', ToolNode(tools))

builder.add_edge(START, 'type_extractor')
builder.add_conditional_edges(
    source='type_extractor',
    path=tools_condition,
    path_map={'tools': 'tools_for_type', '__end__': 'metadata_extractor'},
)
builder.add_edge('tools_for_type', 'type_extractor')

builder.add_conditional_edges(
    source='metadata_extractor',
    path=tools_condition,
    path_map={
        'tools': 'tools_for_metadata',
        '__end__': 'metadata_cleaner',
    },
)
builder.add_edge('tools_for_metadata', 'metadata_extractor')

builder.add_conditional_edges(
    source='metadata_cleaner',
    path=tools_condition,
    path_map={
        'tools': 'tools_for_cleaner',
        '__end__': 'finalize_metadata',
    },
)
builder.add_edge('tools_for_cleaner', 'metadata_cleaner')
builder.add_edge('finalize_metadata', '__end__')

graph = builder.compile()


if __name__ == '__main__':
    digest_hr = 'dkGJT3drmokocKeOni90TR9qsgdIURN6kTmBFe0lnfU='
    digest_ar = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='

    context = ContextSchema(
        digest=digest_hr,
        collection_name='default',
        tenant_id=UUID('ae579baf-91c2-4497-abf5-44867e06c7a1'),
    )

    res = graph.invoke({}, config={'configurable': context.model_dump()})
    print(res)
