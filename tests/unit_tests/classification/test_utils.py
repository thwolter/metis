import numpy as np

from classification.utils import l2


def test_l2_normalization_basic():
    v = np.array([[3.0, 4.0]])  # norm 5
    out = l2(v)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
    # zero vector stays zero, no NaNs
    z = np.array([[0.0, 0.0]])
    outz = l2(z)
    assert np.allclose(outz, z)
    assert not np.isnan(outz).any()
