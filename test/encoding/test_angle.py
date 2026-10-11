"""Angle encoding."""

import numpy as np
import pytest

from shadowsim.encoding import AngleEncoding


def test_encode_single_qubit_matches_ry():
    theta = 0.7
    state = AngleEncoding().encode([theta])
    expected = np.array([np.cos(0.5 * theta), np.sin(0.5 * theta)], dtype=np.complex128)
    assert state.get_num_qubits() == 1
    assert np.allclose(state.to_numpy(), expected)


def test_encode_two_qubits_matches_independent_kronecker_product():
    theta0 = 0.3
    theta1 = -1.1
    state = AngleEncoding().encode([theta0, theta1])
    q0 = np.array([np.cos(0.5 * theta0), np.sin(0.5 * theta0)], dtype=np.complex128)
    q1 = np.array([np.cos(0.5 * theta1), np.sin(0.5 * theta1)], dtype=np.complex128)
    assert state.get_num_qubits() == 2
    assert np.allclose(state.to_numpy(), np.kron(q0, q1))


def test_encode_zero_angle_is_ground_state():
    state = AngleEncoding().encode([0.0, 0.0])
    expected = np.zeros(4, dtype=np.complex128)
    expected[0] = 1.0
    assert np.allclose(state.to_numpy(), expected)


def test_encode_rejects_empty_angles():
    with pytest.raises(ValueError, match="finite real"):
        AngleEncoding().encode([])


def test_encode_rejects_non_finite_angles():
    with pytest.raises(ValueError, match="finite real"):
        AngleEncoding().encode([0.0, np.nan])
    with pytest.raises(ValueError, match="finite real"):
        AngleEncoding().encode([np.inf])


def test_encode_rejects_complex_angles():
    with pytest.raises(ValueError, match="finite real"):
        AngleEncoding().encode([1.0 + 0.0j])


def test_encode_rejects_non_vector_angles():
    with pytest.raises(ValueError, match="finite real"):
        AngleEncoding().encode([[0.1, 0.2]])
