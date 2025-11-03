from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

from .schemas import MetadataSchema


class State(TypedDict, total=False):
    """Graph state tracking conversation history and metadata extraction."""

    messages: Annotated[list[AnyMessage], add_messages]
    metadata: MetadataSchema
