"""Attribute-centric extraction package."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .graph import build_extraction_graph, run_extraction
    from .schemas import ExtractionRequest, ExtractionResult


def __getattr__(name: str) -> Any:
    """Lazily expose heavy submodules to avoid importing chat models during tests."""
    if name in {'build_extraction_graph', 'run_extraction'}:
        graph = import_module('extraction.graph')
        return getattr(graph, name)
    if name in {'ExtractionRequest', 'ExtractionResult'}:
        schemas = import_module('extraction.schemas')
        return getattr(schemas, name)
    message = f'module {__name__} has no attribute {name!r}'
    raise AttributeError(message)


__all__ = ['build_extraction_graph', 'run_extraction', 'ExtractionRequest', 'ExtractionResult']
