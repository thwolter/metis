from __future__ import annotations

import ast
import json
from typing import Any, Mapping, Sequence

import numpy as np


def l2(x: np.ndarray) -> np.ndarray:
    """Normalize vectors to unit length using L2 norm."""
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def as_float_vec1d(
    x: np.ndarray | Sequence[float] | float | int | np.floating[Any] | np.integer[Any],
) -> np.ndarray:
    """Enforce numeric shape and type on an already numeric array or sequence."""
    v = np.asarray(x, dtype=float)
    return v.reshape(1) if v.ndim == 0 else v.reshape(-1)


async def normalise_vector(val) -> np.ndarray[tuple[Any, ...], np.dtype[Any]]:
    """Parse input (JSON, bytes, list, etc.) into a 1-D float vector."""
    if isinstance(val, (list, tuple, np.ndarray)):
        emb = np.asarray(val, dtype=float)
    else:
        # Handle pgvector returned as text/bytea
        if isinstance(val, memoryview):
            val = val.tobytes().decode()
        if isinstance(val, (bytes, bytearray)):
            val = val.decode()
        try:
            return as_float_vec1d(json.loads(val))
        except Exception:
            return as_float_vec1d(ast.literal_eval(val))
    return emb


def softmax(x: np.ndarray) -> np.ndarray:
    """Compute softmax values for each sets of scores in x."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.array([], dtype=x.dtype)
    x = x - np.max(x)
    ex = np.exp(x)
    s = np.sum(ex)
    if s == 0:
        return np.ones_like(x) / x.size
    return ex / s


def filter_prototypes_by_dim(
    dim: int, protos: Mapping[str, np.ndarray[tuple[Any, ...], np.dtype[Any]]]
) -> tuple[list[Any], list[Any]]:
    """Filter prototypes by dimensionality."""
    C_names = []
    C_cols = []
    for name, p in protos.items():
        p1 = as_float_vec1d(p)
        if p1.size == dim:
            C_names.append(name)
            C_cols.append(p1)
    return C_cols, C_names
