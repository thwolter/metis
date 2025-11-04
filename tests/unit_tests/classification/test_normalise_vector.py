import numpy as np
import pytest

from classification.utils import normalise_vector


async def test_normalise_vector_with_list():
    input_data = [1, 2, 3, 4]
    expected_output = np.array([1.0, 2.0, 3.0, 4.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


async def test_normalise_vector_with_tuple():
    input_data = (5, 6, 7, 8)
    expected_output = np.array([5.0, 6.0, 7.0, 8.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


async def test_normalise_vector_with_ndarray():
    input_data = np.array([9, 10, 11, 12], dtype=int)
    expected_output = np.array([9.0, 10.0, 11.0, 12.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


async def test_normalise_vector_with_json_string():
    input_data = '[13, 14, 15, 16]'
    expected_output = np.array([13.0, 14.0, 15.0, 16.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


async def test_normalise_vector_with_bytes():
    input_data = b'[17, 18, 19, 20]'
    expected_output = np.array([17.0, 18.0, 19.0, 20.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


@pytest.mark.asyncio
async def test_normalise_vector_with_memoryview():
    input_data = memoryview(b'[21, 22, 23, 24]')
    expected_output = np.array([21.0, 22.0, 23.0, 24.0])
    result = await normalise_vector(input_data)
    assert np.array_equal(result, expected_output)


async def test_normalise_vector_with_invalid_string():
    input_data = '{"invalid": "data"}'
    with pytest.raises(TypeError):
        await normalise_vector(input_data)
