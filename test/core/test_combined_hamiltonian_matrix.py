"""Tests for shadowsim.core.combined_hamiltonian_matrix."""

import numpy as np
import pytest

from shadowsim.core.combined_hamiltonian_matrix import combined_hamiltonian_matrix
from shadowsim.core import Hamiltonian
from shadowsim.core import LocalHamiltonian


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
