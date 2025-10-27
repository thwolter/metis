import pathlib
import tomllib
from functools import lru_cache


@lru_cache(maxsize=1)
def load_version() -> str:
    path = pathlib.Path(__file__).resolve().parents[2] / 'pyproject.toml'
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    return data['project']['version']
