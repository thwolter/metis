from __future__ import annotations

from functools import lru_cache

from ..schemas import AttributeConstraints, AttributeSpec, AttributeType, Thresholds
from .registry import register


@lru_cache(maxsize=1)
def annual_report_attributes() -> tuple[AttributeSpec, ...]:
    base_thresholds = Thresholds(min_confidence=0.65, min_chunks=1)

    return (
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


register('annual_report', annual_report_attributes())
