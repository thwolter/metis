from __future__ import annotations

import numpy as np

from classification.utils import softmax


def test_softmax_basic():
    x = np.array([1.0, 2.0, 3.0])
    result = softmax(x)
    expected = np.exp(x - np.max(x)) / np.sum(np.exp(x - np.max(x)))
    assert np.allclose(result, expected)


def test_softmax_large_numbers():
    x = np.array([1000, 1001, 1002])
    result = softmax(x)
    expected = np.exp(x - np.max(x)) / np.sum(np.exp(x - np.max(x)))
    assert np.allclose(result, expected)


def test_softmax_negative_numbers():
    x = np.array([-1.0, -2.0, -3.0])
    result = softmax(x)
    expected = np.exp(x - np.max(x)) / np.sum(np.exp(x - np.max(x)))
    assert np.allclose(result, expected)


def test_softmax_zeroes():
    x = np.array([0.0, 0.0, 0.0])
    result = softmax(x)
    expected = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
    assert np.allclose(result, expected)


def test_softmax_all_equal_elements():
    x = np.array([5.0, 5.0, 5.0])
    result = softmax(x)
    expected = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
    assert np.allclose(result, expected)


def test_softmax_empty_array():
    x = np.array([])
    result = softmax(x)
    expected = np.array([])
    assert np.allclose(result, expected)


def test_softmax_single_element_array():
    x = np.array([5.0])
    result = softmax(x)
    expected = np.array([1.0])
    assert np.allclose(result, expected)
