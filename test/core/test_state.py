"""Tests for src.core.state."""

import numpy as np

from src.core.state import State


def test_state_init_stores_vector_and_metadata():
    vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    s = State(vec, num_qubits=2)
    assert np.allclose(s.get_state(), vec)
    assert s.get_num_qubits() == 2
    assert s.get_local_dim() == 2
