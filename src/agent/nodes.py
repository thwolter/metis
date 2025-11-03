from __future__ import annotations

import json
from typing import Any, Dict

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import Runnable

from .helper import metadata_fields_str
from .schemas import MetadataSchema
from .state import State
from .tools import first_chunks, retriever

type RunnableMsg = Runnable

_base_model = init_chat_model(model='openai:gpt-5', temperature=0)

llm_extract: RunnableMsg = _base_model.bind_tools([first_chunks])

metadata_tools = [retriever, MetadataSchema]
llm_metadata: RunnableMsg = _base_model.bind_tools(metadata_tools, tool_choice='any')

_EMPTY_METADATA = MetadataSchema()


def _history(state: State) -> list[BaseMessage]:
    """Return a copy of the conversation history list."""
    return list(state.get('messages', []))


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
    return {'messages': [result]}


# todo: we must run more targetet search, not this:
# SEFE Storage GmbH Handelsregister Kassel HRB Registergericht Amtsgericht Kassel Registernummer Umfirmierung
# vormals astora HRB 15690 Gewinnabführungsvertrag GAZPROM Germania Charlottenburg HRB 36569 Bekanntmachung
# Datum
def metadata_extractor(state: State) -> Dict[str, Any]:
    history = _history(state)
    retrieved_str = ''
    field_list = metadata_fields_str(remove=['document_type'], fields=MetadataSchema.model_fields.keys())
    extraction_prompt = SystemMessage(
        content=(
            'You are an expert metadata extractor. Retrieve the most relevant document chunks excluding '
            'these chunk_ids: ' + retrieved_str + '. Then extract the '
            'following metadata fields: ' + field_list + '. '
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
