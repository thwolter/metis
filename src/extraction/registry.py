from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Mapping

from .schemas import AttributeConstraints, AttributeSpec, AttributeType, Thresholds


class UnknownDocumentTypeError(ValueError):
    """Raised when the registry does not contain the requested document type."""


class UnknownAttributeError(ValueError):
    """Raised when a document type does not define the requested attribute."""


_REGISTRY: dict[str, dict[str, AttributeSpec]] = {}


def _register(doc_type: str, specs: Iterable[AttributeSpec]) -> None:
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


@lru_cache(maxsize=1)
def annual_report_attributes() -> tuple[AttributeSpec, ...]:
    base_thresholds = Thresholds(min_confidence=0.65, min_chunks=1)

    return (
        AttributeSpec(
            name='document_type',
            type=AttributeType.STRING,
            description='The type of document, e.g. "Annual Report".',
            thresholds=base_thresholds,
            normaliser='lowercase',
        ),
        AttributeSpec(
            name='company_name',
            type=AttributeType.STRING,
            description='The name of the company.',
            hints=['company name', 'issuer'],
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='parent_company',
            type=AttributeType.STRING,
            description='The parent company of the company.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='ultimate_parent_company',
            type=AttributeType.STRING,
            description='The ultimate parent company of the company.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='reporting_date',
            type=AttributeType.DATE,
            description='The date the report was generated.',
            hints=['report date', 'issued on'],
            thresholds=base_thresholds,
            normaliser='date_iso',
        ),
        AttributeSpec(
            name='reporting_year',
            type=AttributeType.INTEGER,
            description='The reporting year, e.g. 2022.',
            thresholds=Thresholds(min_confidence=0.7, min_chunks=1),
            normaliser='int',
            constraints=AttributeConstraints(min_value=1900),
        ),
        AttributeSpec(
            name='call_date',
            type=AttributeType.DATE,
            description='The date the document was received.',
            thresholds=base_thresholds,
            normaliser='date_iso',
        ),
        AttributeSpec(
            name='company_register',
            type=AttributeType.STRING,
            description='The company register where the document was received.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='register_number',
            type=AttributeType.STRING,
            description="The company's register number.",
            thresholds=base_thresholds,
            hints=['registration number'],
        ),
        AttributeSpec(
            name='language',
            type=AttributeType.STRING,
            description='The language of the document.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='region',
            type=AttributeType.STRING,
            description='The region of the document.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='tags',
            type=AttributeType.LIST_STRING,
            description='Tags for the document.',
            thresholds=base_thresholds,
        ),
        AttributeSpec(
            name='fy_end_date',
            type=AttributeType.DATE,
            description='Financial year-end date.',
            hints=['financial year'],
            thresholds=Thresholds(min_confidence=0.72, min_chunks=1),
            normaliser='date_iso',
        ),
        AttributeSpec(
            name='auditor_opinion',
            type=AttributeType.ENUM,
            description='Audit opinion classification.',
            thresholds=Thresholds(min_confidence=0.75, min_chunks=1),
            constraints=AttributeConstraints(
                enum_values=['unmodified', 'qualified', 'adverse', 'disclaimer'],
                normaliser='lowercase',
            ),
        ),
        AttributeSpec(
            name='isin',
            type=AttributeType.PATTERN,
            description='International Securities Identification Number.',
            thresholds=Thresholds(min_confidence=0.8, min_chunks=1),
            regex_hint='[A-Z]{2}[A-Z0-9]{9}\\d',
            constraints=AttributeConstraints(pattern='[A-Z]{2}[A-Z0-9]{9}\\d'),
            hints=['isin', 'security identification'],
        ),
    )


_register('annual_report', annual_report_attributes())
