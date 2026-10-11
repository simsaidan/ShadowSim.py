"""Amplitude encoding."""

import numpy as np
import pytest

from shadowsim.encoding import AmplitudeEncoding


def test_encode_keeps_normalized_power_of_two_vector():
    amplitudes = np.array([1 / np.sqrt(2), 1 / np.sqrt(2)], dtype=np.complex128)
    state = AmplitudeEncoding().encode(amplitudes)
    assert state.get_num_qubits() == 1
    assert np.allclose(state.to_numpy(), amplitudes)


def test_encode_normalizes_real_vector():
    state = AmplitudeEncoding().encode([3.0, 4.0])
    assert state.get_num_qubits() == 1
    assert np.allclose(state.to_numpy(), np.array([0.6, 0.8], dtype=np.complex128))


def test_encode_pads_to_next_power_of_two():
    state = AmplitudeEncoding().encode([1.0, 1.0, 0.0])
    expected = np.array([1.0, 1.0, 0.0, 0.0], dtype=np.complex128) / np.sqrt(2)
    assert state.get_num_qubits() == 2
    assert np.allclose(state.to_numpy(), expected)


def test_encode_pads_length_one_to_one_qubit():
    state = AmplitudeEncoding().encode([2.0])
    assert state.get_num_qubits() == 1
    assert np.allclose(state.to_numpy(), np.array([1.0, 0.0], dtype=np.complex128))


def test_encode_preserves_global_phase():
    state = AmplitudeEncoding().encode([2.0j, 0.0])
    assert np.allclose(state.to_numpy(), np.array([1.0j, 0.0], dtype=np.complex128))


def test_encode_normalizes_tiny_amplitudes():
    state = AmplitudeEncoding().encode([0.0, 4.0e-162])
    assert np.allclose(state.to_numpy(), np.array([0.0, 1.0], dtype=np.complex128))


def test_encode_rejects_non_numeric_data():
    with pytest.raises(ValueError, match="finite numbers"):
        AmplitudeEncoding().encode(["a", "b"])


def test_encode_rejects_zero_vector():
    with pytest.raises(ValueError, match="non-zero"):
        AmplitudeEncoding().encode([0.0, 0.0, 0.0])


def test_encode_rejects_empty_vector():
    with pytest.raises(ValueError, match="finite numbers"):
        AmplitudeEncoding().encode([])


def test_encode_rejects_non_finite_vector():
    with pytest.raises(ValueError, match="finite numbers"):
        AmplitudeEncoding().encode([1.0, np.nan])
    with pytest.raises(ValueError, match="finite numbers"):
        AmplitudeEncoding().encode([np.inf, 1.0])


def test_encode_rejects_non_vector():
    with pytest.raises(ValueError, match="finite numbers"):
        AmplitudeEncoding().encode([[1.0, 0.0], [0.0, 1.0]])
