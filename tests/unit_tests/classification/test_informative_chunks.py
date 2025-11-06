import json

import numpy as np
import pytest

# Import helpers directly from the module under test
from classification.inference import _select_informative_chunks


@pytest.mark.parametrize(
    'payload,expected_len',
    [
        ([1.0, 2.0, 3.0], 3),
        (np.array([[1.0, 2.0, 3.0]], dtype=object), 3),
        ([[[1.0, 2.0, 3.0]]], 3),
        (json.dumps([1.0, 2.0, 3.0]), 3),
    ],
)
def _make_protos() -> tuple[dict[str, np.ndarray], list[str]]:
    # Two nearly orthogonal centroids in 4D
    mu_a = np.zeros(4)
    mu_a[0] = 1.0
    mu_b = np.zeros(4)
    mu_b[1] = 1.0
    protos = {
        'class_a': mu_a,
        'class_b': mu_b,
    }
    return protos, ['class_a', 'class_b']


def test_select_informative_chunks_basic():
    protos, _ = _make_protos()
    rng = np.random.default_rng(123)
    # 10 chunks near class_b and 2 near class_a
    chunks: list[np.ndarray] = []
    for i in range(12):
        mean = np.array([1.0, 0.0, 0.0, 0.0]) if i < 2 else np.array([0.0, 1.0, 0.0, 0.0])
        chunks.append(mean + 0.05 * rng.normal(size=4))

    idx, score_mat, _ = _select_informative_chunks(
        chunk_embeddings=chunks,
        chunk_headers=None,
        protos=protos,
        header_weights={},
        m_chunk=5,
        weight_scale=0.0,
    )

    assert len(idx) == 5
    assert score_mat.shape == (12, 2)
    # The most informative chunks should come from the majority class (class_b)
    # Check that at least 3/5 top chunks favour class_b
    top_scores = score_mat[idx, :]
    winners = (top_scores[:, 1] > top_scores[:, 0]).sum()
    assert winners >= 3


def test_select_informative_chunks_with_headers():
    protos, names = _make_protos()
    # all chunks ambiguous around (0.7, 0.7) in subspace -> header should tip to class_a
    chunks = [np.array([0.7, 0.7, 0.0, 0.0]) for _ in range(6)]

    header_weights = {
        'class_a': [('management report', False, 2.0)],
        'class_b': [('register', False, 0.0)],
    }
    headers = ['Management Report'] * 6

    idx, score_mat, class_names = _select_informative_chunks(
        chunk_embeddings=chunks,
        chunk_headers=headers,
        protos=protos,
        header_weights=header_weights,
        m_chunk=4,
        weight_scale=0.05,
    )

    assert len(idx) == 4
    # header bonus should lift class_a over class_b on selected rows
    assert np.all((score_mat[idx, 0] - score_mat[idx, 1]) > -1e-6)
    assert class_names == names
