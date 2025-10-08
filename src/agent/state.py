
from langchain_core.messages import AnyMessage
from typing_extensions import Annotated, TypedDict

from langgraph.graph.message import add_messages

from .schemas import MetadataSchema


def _prefer_metadata(current: MetadataSchema | None, value: MetadataSchema | None) -> MetadataSchema | None:
    """Reducer that prefers the most recent non-null metadata bundle."""
    return value or current


class State(TypedDict, total=False):
    """Graph state tracking conversation history and metadata extraction."""

    messages: Annotated[list[AnyMessage], add_messages]
    metadata: Annotated[MetadataSchema | None, _prefer_metadata]
