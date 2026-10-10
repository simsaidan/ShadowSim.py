"""Property catalog: ``State`` validation.

Invariants exercised by Hypothesis tests in this module:

* Random normalized vectors of length ``local_dim**n`` are accepted.
* Incorrect length or non-unit norm is rejected.
"""

import numpy as np
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL, normalize_state_vector, normalized_states

from shadowsim.core import State


@given(normalized_states())
def test_state_accepts_normalized_vectors(sample: tuple[np.ndarray, int, int]):
    vec, n, local_dim = sample
    state = State(vec, num_qubits=n, local_dim=local_dim)
    assert state.get_num_qubits() == n
    assert state.get_local_dim() == local_dim
    assert np.allclose(state.get_state(), vec, atol=ATOL, rtol=RTOL)
    assert np.isclose(np.linalg.norm(state.get_state()), 1.0)


@given(st.integers(min_value=1, max_value=MAX_PROPERTY_QUBITS), st.integers(min_value=0, max_value=2**31 - 1))
def test_state_rejects_non_normalized_vectors(n: int, seed: int):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(2**n) + 1j * rng.standard_normal(2**n)
    vec = raw * 2.0
    assume(not np.isclose(np.linalg.norm(vec), 1.0))
    with pytest.raises(ValueError, match="normalized"):
        State(vec, num_qubits=n)


@given(st.integers(min_value=1, max_value=MAX_PROPERTY_QUBITS), st.integers(min_value=0, max_value=2**31 - 1))
def test_state_rejects_wrong_length(n: int, seed: int):
    rng = np.random.default_rng(seed)
    wrong_len = 2**n + 1
    raw = rng.standard_normal(wrong_len) + 1j * rng.standard_normal(wrong_len)
    vec = normalize_state_vector(raw)
    with pytest.raises(ValueError, match="length must match"):
        State(vec, num_qubits=n)
