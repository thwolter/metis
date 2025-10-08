"""New LangGraph Agent.

This module defines a custom graph.
"""

# During tests, disable LangSmith/Tracing to avoid external network/auth.
import os

if os.environ.get("PYTEST_CURRENT_TEST"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    # Remove API key to prevent client initialization with invalid credentials
    os.environ.pop("LANGSMITH_API_KEY", None)

from agent.graph import graph

__all__ = ["graph"]
