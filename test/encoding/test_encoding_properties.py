"""Property catalog: state encodings.

Invariants exercised by Hypothesis tests in this module:

* Valid inputs produce a normalized ``State`` of length ``2**num_qubits``.
* Computational-basis index and bit-string inputs agree.
* Angle encoding matches an independent Kronecker product of ``Ry`` states.
* Amplitude encoding matches zero-padding and L2 normalization.
"""

import numpy as np
from hypothesis import assume, given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL

from shadowsim.encoding import AmplitudeEncoding, AngleEncoding, ComputationalBasisEncoding
from shadowsim.utils.next_power_of_two import next_power_of_two

_real = st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False, allow_subnormal=False)


def _assert_normalized_state(vector: np.ndarray, num_qubits: int) -> None:
    assert vector.shape == (2**num_qubits,)
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=ATOL, rtol=RTOL)


@given(
    st.integers(min_value=1, max_value=MAX_PROPERTY_QUBITS),
    st.integers(min_value=0, max_value=2**MAX_PROPERTY_QUBITS - 1),
)
def test_basis_index_is_normalized_one_hot(num_qubits: int, index: int):
    assume(index < 2**num_qubits)
    state = ComputationalBasisEncoding(num_qubits).encode(index)
    expected = np.zeros(2**num_qubits, dtype=np.complex128)
    expected[index] = 1.0
    assert state.get_num_qubits() == num_qubits
    _assert_normalized_state(state.to_numpy(), num_qubits)
    assert np.array_equal(state.to_numpy(), expected)


@given(st.lists(st.integers(min_value=0, max_value=1), min_size=1, max_size=MAX_PROPERTY_QUBITS))
def test_basis_bit_string_matches_index(bits: list[int]):
    num_qubits = len(bits)
    index = 0
    for bit in bits:
        index = (index << 1) | bit
    encoder = ComputationalBasisEncoding(num_qubits)
    from_bits = encoder.encode(bits)
    from_index = encoder.encode(index)
    assert from_bits.get_num_qubits() == num_qubits
    _assert_normalized_state(from_bits.to_numpy(), num_qubits)
    assert np.array_equal(from_bits.to_numpy(), from_index.to_numpy())


@given(st.lists(_real, min_size=1, max_size=MAX_PROPERTY_QUBITS))
def test_angle_encoding_matches_kronecker_product(angles: list[float]):
    state = AngleEncoding().encode(angles)
    expected = np.array([1.0], dtype=np.complex128)
    for theta in angles:
        qubit = np.array([np.cos(0.5 * theta), np.sin(0.5 * theta)], dtype=np.complex128)
        expected = np.kron(expected, qubit)
    assert state.get_num_qubits() == len(angles)
    _assert_normalized_state(state.to_numpy(), len(angles))
    assert np.allclose(state.to_numpy(), expected, atol=ATOL, rtol=RTOL)


@given(st.lists(st.tuples(_real, _real), min_size=1, max_size=2**MAX_PROPERTY_QUBITS))
def test_amplitude_encoding_is_padded_and_normalized(parts: list[tuple[float, float]]):
    amplitudes = [re + 1j * im for re, im in parts]
    assume(np.linalg.norm(amplitudes) != 0.0)
    state = AmplitudeEncoding().encode(amplitudes)
    raw = np.asarray(amplitudes, dtype=np.complex128)
    scale = float(np.max(np.abs(raw)))
    assume(scale > 0.0)
    scaled = raw / scale
    padded_length = max(2, next_power_of_two(int(raw.shape[0])))
    expected = np.zeros(padded_length, dtype=np.complex128)
    expected[: scaled.shape[0]] = scaled
    expected /= np.linalg.norm(scaled)
    num_qubits = padded_length.bit_length() - 1
    assert state.get_num_qubits() == num_qubits
    _assert_normalized_state(state.to_numpy(), num_qubits)
    assert np.allclose(state.to_numpy(), expected, atol=ATOL, rtol=RTOL)
