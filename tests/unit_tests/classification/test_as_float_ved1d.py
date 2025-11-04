# tests/unit_tests/classification/test_utils.py

from __future__ import annotations

import numpy as np

from classification.utils import as_float_vec1d


def test_as_float_vec1d_with_1d_array():
    input_array = np.array([1.0, 2.0, 3.0])
    expected_output = np.array([1.0, 2.0, 3.0])  # Should remain unchanged as 1D
    result = as_float_vec1d(input_array)
    assert np.array_equal(expected_output, result), f'Expected {expected_output}, got {result}'


def test_as_float_vec1d_with_scalar():
    scalar = 5.0
    expected_output = np.array([5.0])
    result = as_float_vec1d(scalar)
    assert np.array_equal(expected_output, result), f'Expected {expected_output}, got {result}'


def test_as_float_vec1d_with_2d_array():
    input_array = np.array([[1.0, 2.0], [3.0, 4.0]])
    expected_output = np.array([1.0, 2.0, 3.0, 4.0])  # Flattened to 1D
    result = as_float_vec1d(input_array)
    assert np.array_equal(expected_output, result), f'Expected {expected_output}, got {result}'


def test_as_float_vec1d_with_sequence():
    sequence = [1.5, 2.5, 3.5]
    expected_output = np.array([1.5, 2.5, 3.5])
    result = as_float_vec1d(sequence)
    assert np.array_equal(expected_output, result), f'Expected {expected_output}, got {result}'


def test_as_float_vec1d_with_empty_array():
    input_array = np.array([])
    expected_output = np.array([])
    result = as_float_vec1d(input_array)
    assert np.array_equal(expected_output, result), f'Expected {expected_output}, got {result}'
