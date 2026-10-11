"""Binary-reflected Gray encoding."""

import numpy as np
import pytest
from strategies.pauli_random import MAX_PROPERTY_QUBITS

from shadowsim.encoding import GrayEncoding

_TWO_QUBIT_GRAY_INDEX = (0, 1, 3, 2)


def _one_hot(dimension: int, index: int) -> np.ndarray:
    """Return a complex one-hot vector of length ``dimension``."""
    vector = np.zeros(dimension, dtype=np.complex128)
    vector[index] = 1.0
    return vector


def _basis_index(state: np.ndarray) -> int:
    """Return the single occupied basis index of a one-hot state."""
    occupied = np.flatnonzero(state)
    assert occupied.shape == (1,)
    return int(occupied[0])


def test_encode_two_qubit_gray_map():
    encoder = GrayEncoding(2)
    for k, index in enumerate(_TWO_QUBIT_GRAY_INDEX):
        state = encoder.encode(k)
        assert state.get_num_qubits() == 2
        assert np.array_equal(state.to_numpy(), _one_hot(4, index))


def test_encode_bit_string_matches_binary_index():
    encoder = GrayEncoding(2)
    assert np.array_equal(encoder.encode([1, 0]).to_numpy(), encoder.encode(2).to_numpy())
    assert np.array_equal(encoder.encode([1, 0]).to_numpy(), _one_hot(4, 3))
    assert np.array_equal(encoder.encode([0, 1]).to_numpy(), encoder.encode(1).to_numpy())


def test_consecutive_indices_differ_by_one_bit():
    for num_qubits in range(1, MAX_PROPERTY_QUBITS + 1):
        encoder = GrayEncoding(num_qubits)
        previous = _basis_index(encoder.encode(0).to_numpy())
        for k in range(2**num_qubits - 1):
            current = _basis_index(encoder.encode(k + 1).to_numpy())
            assert (previous ^ current).bit_count() == 1
            previous = current


def test_encode_accepts_numpy_integer_index():
    state = GrayEncoding(1).encode(np.int64(1))
    assert np.array_equal(state.to_numpy(), np.array([0.0, 1.0], dtype=np.complex128))


def test_encode_accepts_float_bits_that_are_zero_or_one():
    state = GrayEncoding(2).encode([1.0, 0.0])
    assert np.array_equal(state.to_numpy(), _one_hot(4, 3))


def test_encode_rejects_index_out_of_range():
    encoder = GrayEncoding(2)
    with pytest.raises(ValueError, match="basis index"):
        encoder.encode(-1)
    with pytest.raises(ValueError, match="basis index"):
        encoder.encode(4)


def test_encode_rejects_wrong_bit_length():
    with pytest.raises(ValueError, match="bit string length"):
        GrayEncoding(3).encode([1, 0])


def test_encode_rejects_bits_other_than_zero_or_one():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        GrayEncoding(2).encode([1, 2])


def test_encode_rejects_bool_index():
    with pytest.raises(ValueError, match="integer index or a 1D sequence"):
        GrayEncoding(1).encode(True)


def test_encode_accepts_zero_dimensional_integer():
    state = GrayEncoding(2).encode(np.array(2))
    assert np.array_equal(state.to_numpy(), _one_hot(4, 3))


def test_encode_rejects_zero_dimensional_float():
    with pytest.raises(ValueError, match="integer index or a 1D sequence"):
        GrayEncoding(1).encode(np.float64(1.0))


def test_encode_rejects_non_numeric_bits():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        GrayEncoding(2).encode(["0", "1"])


def test_encode_rejects_non_finite_bits():
    with pytest.raises(ValueError, match="each bit must be 0 or 1"):
        GrayEncoding(2).encode([0.0, np.nan])


def test_encode_rejects_two_dimensional_bits():
    with pytest.raises(ValueError, match="bit string length"):
        GrayEncoding(2).encode([[1, 0], [0, 1]])


def test_constructor_rejects_invalid_num_qubits():
    with pytest.raises(AssertionError, match="non-negative"):
        GrayEncoding(-1)
    with pytest.raises(AssertionError, match="must be an integer"):
        GrayEncoding(1.5)
