from __future__ import annotations

from typing import Any, Dict

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from pydantic import ValidationError

from .schemas import MetadataSchema
from .state import State
from .tools import first_chunks, retriever, search_tool

_base_model = init_chat_model(model="openai:gpt-5-mini", temperature=0)
tools = [retriever, first_chunks, search_tool]

model_with_tools = _base_model.bind_tools(tools)
structured_metadata_model = _base_model.with_structured_output(MetadataSchema)

_EMPTY_METADATA = MetadataSchema()


def _metadata_fields(remove_document_type: bool = True) -> str:
    fields = list(MetadataSchema.model_fields.keys())
    if remove_document_type:
        fields.remove('document_type')
    return ', '.join(fields)


def _history(state: State) -> list[BaseMessage]:
    """Return a copy of the conversation history list."""
    return list(state.get("messages", []))


def _metadata_message(metadata: MetadataSchema) -> AIMessage:
    """Create a message that records the structured metadata in the transcript."""
    return AIMessage(content=metadata.model_dump_json(indent=2))



def type_extractor(state: State) -> Dict[str, Any]:
    sys_msg = SystemMessage(
        content=(
            "You are an expert document classifier. Retrieve and analyse the first document chunks "
            "and their metadata to classify the document (Annual Report, Management Report, Balance Sheet, "
            "Commercial Register Extract, or Other). Start by retrieving a few chunks; if that is insufficient, "
            "retrieve more chunks and skipping already received chunks."
        )
    )
    history = _history(state)
    result = model_with_tools.invoke([sys_msg] + history)
    return {"messages": [result]}


def metadata_extractor(state: State) -> Dict[str, Any]:
    history = _history(state)
    extraction_prompt = SystemMessage(
        content=(
            "You are an expert metadata extractor. Retrieve relevant documents "
            "chunks and extracts the following metadata fields: " + _metadata_fields() +
            ". Ensure that the correct company name is identified, e.g. when a company was renamed."
            " When you are uncertain about a field, use the search tool to increase confidence. "
            " Retrieve up to two times further chunks when you are uncertain about a field."
        )
    )

    tool_result = model_with_tools.invoke([extraction_prompt] + history)
    update: Dict[str, Any] = {"messages": [tool_result]}

    if getattr(tool_result, "tool_calls", None):
        # Still need to execute tools; do not attempt to parse yet.
        return update

    structured_prompt = SystemMessage(
        content=(
            "Using the conversation so far, respond with JSON matching the metadata schema precisely. "
            "Use null for missing fields and do not include any explanatory text."
        )
    )

    try:
        metadata = structured_metadata_model.invoke(
            [structured_prompt, *history, tool_result]
        )
    except ValidationError:
        metadata = _EMPTY_METADATA

    update.setdefault("messages", []).append(_metadata_message(metadata))
    update["metadata"] = metadata
    return update


def metadata_cleaner(state: State) -> Dict[str, Any]:
    history = _history(state)
    current_metadata = state.get("metadata") or _EMPTY_METADATA
    metadata_context = AIMessage(
        content="Current metadata candidate:\n"
        + current_metadata.model_dump_json(indent=2)
    )

    cleaner_prompt = SystemMessage(
        content=(
            "You are an expert metadata cleaner. Review the existing metadata and the available context. "
            "You may retrieve additional document chunks or use the search tool when you are uncertain about a field. "
            "Ensure company names are the legal names."
        )
    )

    tool_result = model_with_tools.invoke(
        [cleaner_prompt, *history, metadata_context]
    )
    update: Dict[str, Any] = {"messages": [tool_result]}

    if getattr(tool_result, "tool_calls", None):
        return update

    structured_prompt = SystemMessage(
        content=(
            "Produce the final metadata as JSON valid for the metadata schema. "
            "Keep values precise, use null where information is unavailable, and do not add commentary."
        )
    )

    try:
        metadata = structured_metadata_model.invoke(
            [structured_prompt, *history, metadata_context, tool_result]
        )
    except ValidationError:
        metadata = current_metadata

    update.setdefault("messages", []).append(_metadata_message(metadata))
    update["metadata"] = metadata
    return update


def finalize_metadata(state: State) -> Dict[str, Any]:
    metadata = state.get("metadata") or _EMPTY_METADATA
    metadata_dict = metadata.model_dump()
    return {"metadata": metadata, **metadata_dict}
