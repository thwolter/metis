from __future__ import annotations

import json
from typing import Any, Dict, Iterable


def non_negative_int(value: Any) -> int:
    """Convert a value to a non-negative int, treating invalid inputs as zero."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def metadata_fields_str(remove: list | None, *, fields: Iterable[str]) -> str:
    field_list = list(fields)
    if remove:
        field_list = [x for x in field_list if x not in remove]
    return ', '.join(field_list)


def normalize_args(raw_args: Any) -> Dict[str, Any]:
    if raw_args is None:
        return {}
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}
    if isinstance(raw_args, dict):
        return raw_args
    if hasattr(raw_args, 'model_dump'):
        return raw_args.model_dump()
    if hasattr(raw_args, 'dict'):
        return raw_args.dict()
    return {}
