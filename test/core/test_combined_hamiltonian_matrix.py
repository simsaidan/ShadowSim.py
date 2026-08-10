"""Tests for shadowsim.core.combined_hamiltonian_matrix."""

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, LocalHamiltonian
from shadowsim.core.combined_hamiltonian_matrix import combined_hamiltonian_matrix


def test_combined_hamiltonian_matrix_sums_full_and_local_terms():
    local = LocalHamiltonian(np.diag([1.0, -1.0]), sites=[0], local_dim=2)
    full = Hamiltonian(np.diag([0.5, 0.5]))
    out = combined_hamiltonian_matrix([local, full], num_qubits=1)
    assert out.shape == (2, 2)
    assert np.allclose(out, np.diag([1.5, -0.5]))


def test_combined_hamiltonian_matrix_rejects_mixed_local_dims():
    h2 = LocalHamiltonian(np.diag([1.0, -1.0]), sites=[0], local_dim=2)
    h3 = LocalHamiltonian(np.diag([1.0, 0.0, -1.0]), sites=[0], local_dim=3)
    with pytest.raises(ValueError, match="mixed local_dim"):
        combined_hamiltonian_matrix([h2, h3], num_qubits=1)


def test_combined_hamiltonian_matrix_embeds_local_with_identity_padding():
    # Local on middle qubit of a 3-qubit chain → n_before > 0 and n_after > 0.
    local = LocalHamiltonian(np.diag([1.0, -1.0]), sites=[1], local_dim=2)
    out = combined_hamiltonian_matrix([local], num_qubits=3)
    expected = np.kron(np.eye(2), np.kron(np.diag([1.0, -1.0]), np.eye(2)))
    assert out.shape == (8, 8)
    assert np.allclose(out, expected)


def test_combined_hamiltonian_matrix_rejects_disagreeing_dimensions():
    local = LocalHamiltonian(np.diag([1.0, -1.0]), sites=[0], local_dim=2)
    full = Hamiltonian(np.eye(4, dtype=np.complex128))
    with pytest.raises(ValueError, match="dimensions disagree"):
        combined_hamiltonian_matrix([local, full], num_qubits=1)
