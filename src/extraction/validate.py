from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Callable, Iterable, Sequence

from .schemas import (
    AttributeConstraints,
    AttributeResult,
    AttributeSpec,
    AttributeType,
    ValidationIssue,
)

Normaliser = Callable[[Any], Any]


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool, date, datetime)):
        return str(value)
    try:
        return json.dumps(value)
    except TypeError:
        return None


def _normalise_date(value: Any) -> tuple[date | None, list[ValidationIssue]]:
    if value is None:
        return None, []
    if isinstance(value, date) and not isinstance(value, datetime):
        return value, []
    text = _to_str(value)
    if not text:
        return None, [ValidationIssue(code='type', message='Expected date value')]

    text = text.strip()
    formats = (
        '%Y-%m-%d',
        '%d.%m.%Y',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%B %d %Y',
        '%d %B %Y',
        '%b %d %Y',
        '%d %b %Y',
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.date(), []
        except ValueError:
            continue
    if len(text) == 4 and text.isdigit():
        return date(int(text), 1, 1), []
    return None, [ValidationIssue(code='type', message=f'Could not parse date value: {text!r}')]


def _normalise_int(value: Any) -> tuple[int | None, list[ValidationIssue]]:
    if value is None:
        return None, []
    if isinstance(value, bool):
        return int(value), []
    if isinstance(value, (int,)):
        return int(value), []
    text = _to_str(value)
    if not text:
        return None, [ValidationIssue(code='type', message='Expected integer')]
    cleaned = text.replace(',', '').replace(' ', '')
    if cleaned.endswith('.0'):
        cleaned = cleaned[:-2]
    if cleaned.isdigit() or (cleaned.startswith('-') and cleaned[1:].isdigit()):
        return int(cleaned), []
    return None, [ValidationIssue(code='type', message=f'Invalid integer literal: {text!r}')]


def _normalise_float(value: Any) -> tuple[float | None, list[ValidationIssue]]:
    if value is None:
        return None, []
    if isinstance(value, (int, float)):
        return float(value), []
    text = _to_str(value)
    if not text:
        return None, [ValidationIssue(code='type', message='Expected float')]
    cleaned = text.replace(',', '').replace(' ', '')
    try:
        return float(cleaned), []
    except ValueError:
        return None, [ValidationIssue(code='type', message=f'Invalid float literal: {text!r}')]


def _normalise_date_iso(value: Any) -> str | None:
    normalised_date, _ = _normalise_date(value)
    if normalised_date is None:
        return None
    return normalised_date.isoformat()


def _apply_normaliser(name: str, value: Any) -> Any:
    mapping: dict[str, Normaliser] = {
        'lowercase': lambda v: v.lower() if isinstance(v, str) else v,
        'uppercase': lambda v: v.upper() if isinstance(v, str) else v,
        'title_case': lambda v: v.title() if isinstance(v, str) else v,
        'strip_whitespace': lambda v: v.strip() if isinstance(v, str) else v,
        'int': lambda v: _normalise_int(v)[0],
        'float': lambda v: _normalise_float(v)[0],
        'date_iso': _normalise_date_iso,
    }
    func = mapping.get(name)
    if func is None:
        return value
    return func(value)


def _validate_enum(value: Any, enum_values: Sequence[str]) -> list[ValidationIssue]:
    if value is None:
        return []
    if isinstance(value, str):
        if value in enum_values:
            return []
        return [ValidationIssue(code='enum', message=f'Value {value!r} not in {enum_values!r}')]
    return [ValidationIssue(code='enum', message='Enum value must be a string')]


def _validate_pattern(value: Any, pattern: str) -> list[ValidationIssue]:
    if value is None:
        return []
    text = _to_str(value)
    if text is None:
        return [ValidationIssue(code='pattern', message='Value must be string-like')]
    if re.fullmatch(pattern, text):
        return []
    return [ValidationIssue(code='pattern', message=f'Value {text!r} does not match pattern {pattern!r}')]


def _validate_range(value: Any, constraints: AttributeConstraints) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    numeric_value: float | None
    if isinstance(value, (int, float)):
        numeric_value = float(value)
    else:
        as_float, errs = _normalise_float(value)
        issues.extend(errs)
        numeric_value = as_float
    if numeric_value is None:
        return issues

    if constraints.min_value is not None and numeric_value < constraints.min_value:
        issues.append(
            ValidationIssue(code='range', message=f'Value {numeric_value} below minimum {constraints.min_value}')
        )
    if constraints.max_value is not None and numeric_value > constraints.max_value:
        issues.append(
            ValidationIssue(code='range', message=f'Value {numeric_value} above maximum {constraints.max_value}')
        )
    return issues


def _normalise_list(values: Iterable[Any]) -> list[str]:
    normalised: list[str] = []
    for item in values:
        text = _to_str(item)
        if text is not None:
            normalised.append(text.strip())
    return normalised


def validate_and_normalise(value: Any, spec: AttributeSpec) -> tuple[Any | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    result = value

    if spec.normaliser:
        result = _apply_normaliser(spec.normaliser, result)

    if spec.constraints and spec.constraints.normaliser:
        result = _apply_normaliser(spec.constraints.normaliser, result)

    attr_type = spec.type
    constraints = spec.constraints

    if attr_type == AttributeType.DATE:
        result, errs = _normalise_date(result)
        issues.extend(errs)
        if result is not None:
            result = result.isoformat()
    elif attr_type == AttributeType.INTEGER:
        result, errs = _normalise_int(result)
        issues.extend(errs)
    elif attr_type == AttributeType.FLOAT:
        result, errs = _normalise_float(result)
        issues.extend(errs)
    elif attr_type == AttributeType.BOOLEAN:
        if isinstance(result, bool):
            pass
        elif isinstance(result, str):
            lowered = result.strip().lower()
            if lowered in {'true', 'yes', '1'}:
                result = True
            elif lowered in {'false', 'no', '0'}:
                result = False
            else:
                issues.append(ValidationIssue(code='type', message='Invalid boolean literal'))
        elif result is None:
            result = None
        else:
            issues.append(ValidationIssue(code='type', message='Invalid boolean literal'))
    elif attr_type == AttributeType.LIST_STRING:
        if result is None:
            result = []
        elif isinstance(result, (list, tuple, set)):
            result = _normalise_list(result)
        else:
            text = _to_str(result)
            if text is None:
                issues.append(ValidationIssue(code='type', message='List value must be iterable'))
                result = []
            else:
                result = _normalise_list([part.strip() for part in text.split(',')])
    elif attr_type == AttributeType.JSON:
        if result is None:
            result = None
        elif isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                issues.append(ValidationIssue(code='type', message='Invalid JSON value'))
    else:
        # default string coercion
        if result is not None and not isinstance(result, str):
            text = _to_str(result)
            if text is None:
                issues.append(ValidationIssue(code='type', message='Value must be string'))
                result = None
            else:
                result = text.strip()

    if constraints:
        if constraints.enum_values:
            issues.extend(_validate_enum(result, constraints.enum_values))
        if constraints.pattern:
            issues.extend(_validate_pattern(result, constraints.pattern))
        if constraints.min_value is not None or constraints.max_value is not None:
            issues.extend(_validate_range(result, constraints))

    return result, issues


def apply_validation(
    *,
    attribute: AttributeSpec,
    value: Any,
    confidence: float,
    chunk_count: int,
    provenance: Sequence[str],
) -> AttributeResult:
    normalised_value, issues = validate_and_normalise(value, attribute)
    status = 'accepted' if not issues else 'accepted'
    return AttributeResult(
        name=attribute.name,
        value=normalised_value,
        confidence=confidence,
        provenance=tuple(provenance),
        validation_issues=tuple(issues),
        chunk_count=chunk_count,
        status=status,
    )
