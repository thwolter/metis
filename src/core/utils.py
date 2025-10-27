import json
import pathlib
import tomllib
from functools import lru_cache


@lru_cache(maxsize=1)
def load_version() -> str:
    try:
        path = pathlib.Path(__file__).resolve().parents[2] / 'pyproject.toml'
        with open(path, 'rb') as f:
            data = tomllib.load(f)
        return data['project']['version']
    except FileNotFoundError:
        return 'unknown'


def parse_cors_origins(value: str | list[str] | None) -> tuple[str, ...]:
    if not value:
        return ()
    if value in ('*', '"*"'):
        return ('*',)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                return (parsed.strip().rstrip('/'),)
            if isinstance(parsed, (list, tuple)):
                return tuple(o.strip().rstrip('/') for o in parsed)
        except json.JSONDecodeError:
            return tuple(o.strip().rstrip('/') for o in value.split(',') if o.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(o).strip().rstrip('/') for o in value)
    return (str(value).strip().rstrip('/'),)
