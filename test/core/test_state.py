"""Tests for src.core.state."""

import numpy as np
import pytest

from src.core.state import State, _as_valid_state_vector


def test_state_init_stores_vector_and_metadata():
    vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    s = State(vec, num_qubits=2)
    assert np.allclose(s.get_state(), vec)
    assert s.get_num_qubits() == 2
    assert s.get_local_dim() == 2


def test_state_init_accepts_normalized_superposition():
    vec = np.array([1 / np.sqrt(2), 1 / np.sqrt(2)], dtype=np.complex128)
    s = State(vec, num_qubits=1)
    assert np.allclose(s.get_state(), vec)


def test_state_init_rejects_non_normalized_vector():
    vec = np.array([1.0, 1.0], dtype=np.complex128)
    with pytest.raises(ValueError, match="normalized"):
        State(vec, num_qubits=1)


def test_state_init_accepts_row_vector_input():
    row = np.array([[1.0, 0.0]], dtype=np.complex128)
    s = State(row, num_qubits=1)
    assert s.get_state().shape == (2,)
    assert np.allclose(s.get_state(), np.array([1.0, 0.0], dtype=np.complex128))


def test_state_init_rejects_wrong_length_for_qubits():
    vec = np.array([1.0, 0.0, 0.0], dtype=np.complex128)
    with pytest.raises(ValueError, match="state vector length must match"):
        State(vec, num_qubits=1)


def test_state_init_rejects_num_qubits_negative():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    with pytest.raises(AssertionError, match="num_qubits must be non-negative"):
        State(vec, num_qubits=-1)


def test_state_init_rejects_non_integer_num_qubits():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    with pytest.raises((AssertionError, TypeError)):
        State(vec, num_qubits="1")
    with pytest.raises((AssertionError, TypeError)):
        State(vec, num_qubits=1.0)


def test_state_init_rejects_invalid_local_dim():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    with pytest.raises(AssertionError, match="local_dim must be a positive integer"):
        State(vec, num_qubits=1, local_dim=0)
    with pytest.raises(AssertionError, match="local_dim must be an integer"):
        State(vec, num_qubits=1, local_dim=2.0)


def test_state_set_state_updates_when_valid():
    s = State(np.array([1.0, 0.0], dtype=np.complex128), num_qubits=1)
    new_vec = np.array([0.0, 1.0], dtype=np.complex128)
    s.set_state(new_vec)
    assert np.allclose(s.get_state(), new_vec)


def test_state_set_state_rejects_invalid_and_keeps_previous():
    original = np.array([1.0, 0.0], dtype=np.complex128)
    s = State(original, num_qubits=1)
    with pytest.raises(ValueError, match="normalized"):
        s.set_state(np.array([1.0, 1.0], dtype=np.complex128))
    assert np.allclose(s.get_state(), original)


def test_state_to_numpy_returns_same_array_reference():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    s = State(vec, num_qubits=1)
    assert s.to_numpy() is s.get_state()


def test_state_str_and_repr_include_metadata():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    s = State(vec, num_qubits=1, local_dim=2)
    text = str(s)
    rep = repr(s)
    assert "State(" in text
    assert "num_qubits=1" in text
    assert "local_dim=2" in text
    assert "shape=(2,)" in text
    assert "State(" in rep
    assert "num_qubits=1" in rep
    assert "local_dim=2" in rep


def test_state_supports_non_qubit_local_dimension():
    vec = np.zeros(9, dtype=np.complex128)
    vec[0] = 1.0
    s = State(vec, num_qubits=2, local_dim=3)
    assert s.get_num_qubits() == 2
    assert s.get_local_dim() == 3
    assert s.get_state().shape == (9,)


def test_as_valid_state_vector_accepts_valid_1d_vector():
    vec = np.array([1.0, 0.0], dtype=np.complex128)
    out = _as_valid_state_vector(vec, num_qubits=1, local_dim=2)
    assert np.allclose(out, vec)
    assert out.ndim == 1


def test_as_valid_state_vector_flattens_row_and_column_vectors():
    row = np.array([[1.0, 0.0]], dtype=np.complex128)
    col = np.array([[1.0], [0.0]], dtype=np.complex128)
    out_row = _as_valid_state_vector(row, num_qubits=1, local_dim=2)
    out_col = _as_valid_state_vector(col, num_qubits=1, local_dim=2)
    assert out_row.shape == (2,)
    assert out_col.shape == (2,)
    assert np.allclose(out_row, np.array([1.0, 0.0], dtype=np.complex128))
    assert np.allclose(out_col, np.array([1.0, 0.0], dtype=np.complex128))


def test_as_valid_state_vector_rejects_full_matrix():
    bad = np.eye(2, dtype=np.complex128)
    with pytest.raises(ValueError, match="state must be a vector"):
        _as_valid_state_vector(bad, num_qubits=1, local_dim=2)


def test_as_valid_state_vector_rejects_wrong_length():
    bad = np.array([1.0, 0.0, 0.0], dtype=np.complex128)
    with pytest.raises(ValueError, match="state vector length must match"):
        _as_valid_state_vector(bad, num_qubits=1, local_dim=2)


def test_as_valid_state_vector_rejects_non_normalized():
    bad = np.array([1.0, 1.0], dtype=np.complex128)
    with pytest.raises(ValueError, match="normalized"):
        _as_valid_state_vector(bad, num_qubits=1, local_dim=2)
