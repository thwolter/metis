from typing import Annotated

from pydantic import StringConstraints

SHA256B64 = Annotated[
    str,
    StringConstraints(min_length=44, max_length=44, pattern=r"^[A-Za-z0-9+/]{43}=$"),
]
