"""Computational-basis encoding."""

import numpy as np
import pytest

from shadowsim.encoding import ComputationalBasisEncoding


def test_encode_index_is_one_hot():
    state = ComputationalBasisEncoding(3).encode(5)
    expected = np.zeros(8, dtype=np.complex128)
    expected[5] = 1.0
    assert state.get_num_qubits() == 3
    assert np.array_equal(state.to_numpy(), expected)


def test_encode_bit_string_matches_index():
    encoder = ComputationalBasisEncoding(2)
    assert np.array_equal(encoder.encode([1, 0]).to_numpy(), encoder.encode(2).to_numpy())
    assert np.array_equal(encoder.encode([0, 1]).to_numpy(), encoder.encode(1).to_numpy())


def test_encode_accepts_numpy_integer_index():
    state = ComputationalBasisEncoding(1).encode(np.int64(1))
    assert np.array_equal(state.to_numpy(), np.array([0.0, 1.0], dtype=np.complex128))


def test_encode_accepts_float_bits_that_are_zero_or_one():
    state = ComputationalBasisEncoding(2).encode([1.0, 0.0])
    expected = np.zeros(4, dtype=np.complex128)
    expected[2] = 1.0
    assert np.array_equal(state.to_numpy(), expected)


def test_encode_rejects_index_out_of_range():
    encoder = ComputationalBasisEncoding(2)
    with pytest.raises(ValueError, match="basis index"):
        encoder.encode(-1)
    with pytest.raises(ValueError, match="basis index"):
        encoder.encode(4)


def test_encode_rejects_wrong_bit_length():
    with pytest.raises(ValueError, match="bit string length"):
        ComputationalBasisEncoding(3).encode([1, 0])


def test_encode_rejects_bits_other_than_zero_or_one():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        ComputationalBasisEncoding(2).encode([1, 2])


def test_encode_rejects_bool_index():
    with pytest.raises(ValueError, match="integer index or a 1D sequence"):
        ComputationalBasisEncoding(1).encode(True)


def test_encode_accepts_zero_dimensional_integer():
    state = ComputationalBasisEncoding(2).encode(np.array(2))
    expected = np.zeros(4, dtype=np.complex128)
    expected[2] = 1.0
    assert np.array_equal(state.to_numpy(), expected)


def test_encode_rejects_zero_dimensional_float():
    with pytest.raises(ValueError, match="integer index or a 1D sequence"):
        ComputationalBasisEncoding(1).encode(np.float64(1.0))


def test_encode_rejects_non_numeric_bits():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        ComputationalBasisEncoding(2).encode(["0", "1"])


def test_encode_rejects_non_finite_bits():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        ComputationalBasisEncoding(2).encode([0.0, np.nan])


def test_encode_rejects_two_dimensional_bits():
    with pytest.raises(ValueError, match="bit string length"):
        ComputationalBasisEncoding(2).encode([[1, 0], [0, 1]])


def test_constructor_rejects_invalid_num_qubits():
    with pytest.raises(AssertionError, match="non-negative"):
        ComputationalBasisEncoding(-1)
    with pytest.raises(AssertionError, match="must be an integer"):
        ComputationalBasisEncoding(1.5)
