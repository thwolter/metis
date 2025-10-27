from __future__ import annotations

import json
from typing import Any, Dict

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import Runnable

from .schemas import MetadataSchema
from .state import State
from .tools import first_chunks, retriever
from .utils import metadata_fields_str, non_negative_int, normalize_args

type RunnableMsg = Runnable

_base_model = init_chat_model(model='openai:gpt-5', temperature=0)

llm_extract: RunnableMsg = _base_model.bind_tools([first_chunks])

metadata_tools = [retriever, MetadataSchema]
llm_metadata: RunnableMsg = _base_model.bind_tools(metadata_tools, tool_choice='any')

_EMPTY_METADATA = MetadataSchema()


def _history(state: State) -> list[BaseMessage]:
    """Return a copy of the conversation history list."""
    return list(state.get('messages', []))


def _metadata_message(metadata: MetadataSchema) -> AIMessage:
    """Create a message that records the structured metadata in the transcript."""
    return AIMessage(content=metadata.model_dump_json(indent=2))


def _tool_call_name(tool_call: Any) -> str | None:
    if isinstance(tool_call, dict):
        return tool_call.get('name')
    return getattr(tool_call, 'name', None)


def _tool_call_args(tool_call: Any) -> Any:
    if isinstance(tool_call, dict):
        if 'args' in tool_call:
            return tool_call['args']
        if 'arguments' in tool_call:
            return tool_call['arguments']
    args = getattr(tool_call, 'args', None)
    if args is None:
        args = getattr(tool_call, 'arguments', None)
    return args


def _retrieved_first_chunks(messages: list[BaseMessage | AIMessage]) -> list[int]:
    """Return how many sequential `first_chunks` have already been requested."""
    retrieved = []
    for message in messages:
        tool_calls = getattr(message, 'tool_calls', None) or []
        for tool_call in tool_calls:
            if _tool_call_name(tool_call) != 'first_chunks':
                continue
            args = normalize_args(_tool_call_args(tool_call))
            k = non_negative_int(args.get('k'))
            skip = non_negative_int(args.get('skip'))
            retrieved = retrieved + list(range(skip, skip + k))
    return retrieved


def type_extractor(state: State) -> Dict[str, Any]:
    sys_msg = SystemMessage(
        content=(
            'You are an expert document classifier. Retrieve and analyse the first document chunks '
            'and their metadata to classify the document (Annual Report, Management Report, Balance Sheet, '
            'Commercial Register Extract, or Other). Start by retrieving a few chunks; if that is insufficient, '
            'retrieve more chunks and skipping already received chunks. If less then requested chunks '
            'are retrieved, then classify the document without further retrieval.'
        )
    )
    history = _history(state)
    result = llm_extract.invoke([sys_msg] + history)
    update: Dict[str, Any] = {'messages': [result]}

    if getattr(result, 'tool_calls', None):
        return update

    update['retrieved_chunks'] = _retrieved_first_chunks(history)
    return update


def metadata_extractor(state: State) -> Dict[str, Any]:
    history = _history(state)
    retrieved = state.get('retrieved_chunks', [])
    retrieved_str = ', '.join([str(x) for x in retrieved])
    extraction_prompt = SystemMessage(
        content=(
            'You are an expert metadata extractor. Retrieve the most relevant document chunks excluding '
            'these chunk_ids: ' + retrieved_str + '. Then extract the '
            'following metadata fields: ' + metadata_fields_str(remove=['document_type']) + '. '
            'Ensure correct identification of the company name, even if it was renamed. '
        )
    )
    tool_result = llm_metadata.invoke([extraction_prompt] + history)
    result: dict[str, Any] = {'messages': [tool_result]}
    if tool_call := getattr(tool_result, 'tool_calls', None):
        if tool_call[0]['name'] == 'MetadataSchema':
            args = tool_result.tool_calls[0]['args']
            if isinstance(args, str):
                args = json.loads(args)  # convert JSON → dict
            md = MetadataSchema.model_validate(args)
            result['metadata'] = md
    return result


def _last_tool_name(messages: list[BaseMessage]) -> str | None:
    """Return the most recent tool invocation name, if any."""
    for message in reversed(messages):
        if getattr(message, 'type', None) != 'tool':
            continue
        name = getattr(message, 'name', None)
        if name:
            return name
    return None


def should_continue(state: State) -> str:
    history = _history(state)
    if not history:
        return 'continue'
    last_tool = _last_tool_name(history)
    if last_tool == 'MetadataSchema':
        return 'finalize'
    return 'continue'


def finalize_metadata(state: State) -> Dict[str, Any]:
    metadata = state['metadata']
    metadata_dict = metadata.model_dump()
    return {'metadata': metadata, **metadata_dict}
