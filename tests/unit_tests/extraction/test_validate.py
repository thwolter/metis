from __future__ import annotations

from datasifter.schemas import AttributeConstraints, AttributeSpec, AttributeType
from datasifter.tools.validate import _validate_and_normalise


def test_validate_and_normalise_date_iso() -> None:
    spec = AttributeSpec(
        name='reporting_date',
        type=AttributeType.DATE,
        description='Report date',
        normaliser='date_iso',
    )
    value, issues = _validate_and_normalise('2024-12-31', spec)
    assert value == '2024-12-31'
    assert issues == []


def test_validate_enum_enforces_allowed_values() -> None:
    spec = AttributeSpec(
        name='auditor_opinion',
        type=AttributeType.ENUM,
        description='Opinion',
        constraints=AttributeConstraints(enum_values=['unmodified', 'qualified']),
    )
    value, issues = _validate_and_normalise('qualified', spec)
    assert value == 'qualified'
    assert issues == []

    _, errors = _validate_and_normalise('unknown', spec)
    assert errors, 'expect validation error for enum mismatch'


def test_validate_pattern() -> None:
    spec = AttributeSpec(
        name='isin',
        type=AttributeType.PATTERN,
        description='ISIN',
        constraints=AttributeConstraints(pattern='[A-Z]{2}[A-Z0-9]{9}\\d'),
    )
    value, issues = _validate_and_normalise('DE0001234567', spec)
    assert value == 'DE0001234567'
    assert issues == []

    _, errors = _validate_and_normalise('12345', spec)
    assert any(issue.code == 'pattern' for issue in errors)
