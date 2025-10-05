from typing import TypedDict, Dict, Any


class State(TypedDict):
    digest: str
    doctype: str
    features: Dict[str, Any]