from __future__ import annotations

from typing import Iterable, Mapping

from extraction.schemas import AttributeSpec


class UnknownDocumentTypeError(ValueError):
    """Raised when the registry does not contain the requested document type."""


class UnknownAttributeError(ValueError):
    """Raised when a document type does not define the requested attribute."""


_REGISTRY: dict[str, dict[str, AttributeSpec]] = {}


def register(doc_type: str, specs: Iterable[AttributeSpec]) -> None:
    doc_type_norm = doc_type.lower()
    bucket = _REGISTRY.setdefault(doc_type_norm, {})
    for spec in specs:
        bucket[spec.name] = spec


def get_registry() -> Mapping[str, Mapping[str, AttributeSpec]]:
    return _REGISTRY


def get_attributes(doc_type: str) -> Mapping[str, AttributeSpec]:
    doc_type_norm = doc_type.lower()
    if doc_type_norm not in _REGISTRY:
        msg = f'Unknown document type: {doc_type}'
        raise UnknownDocumentTypeError(msg)
    return _REGISTRY[doc_type_norm]


def get_attribute_specs(doc_type: str, attribute_names: Iterable[str] | None = None) -> list[AttributeSpec]:
    attributes = get_attributes(doc_type)
    if attribute_names is None:
        return list(attributes.values())

    specs: list[AttributeSpec] = []
    for name in attribute_names:
        if name not in attributes:
            msg = f'Attribute {name} not registered for doc_type {doc_type}'
            raise UnknownAttributeError(msg)
        specs.append(attributes[name])
    return specs
