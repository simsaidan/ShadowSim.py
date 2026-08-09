import numpy as np
import pytest

from shadowsim.core import Hamiltonian
from shadowsim.core import LocalHamiltonian


Z = np.diag([1.0, -1.0]).astype(np.complex128)


def test_local_hamiltonian_to_full_and_accessors():
    local = LocalHamiltonian(Z, sites=[1], local_dim=2)
    full = local.to_full_hamiltonian(total_sites=3)

    assert isinstance(full, Hamiltonian)
    expected = np.kron(np.eye(2), np.kron(Z, np.eye(2)))
    assert np.allclose(full.matrix, expected)
    assert local.get_sites() == [1]
    assert local.get_local_dim() == 2
    assert np.allclose(local.get_matrix(), Z)


def test_local_hamiltonian_to_full_validates_total_sites():
    local = LocalHamiltonian(Z, sites=[1], local_dim=2)
    with pytest.raises(AssertionError, match="total_sites must be an integer"):
        local.to_full_hamiltonian(3.0)  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match="total_sites must be positive"):
        local.to_full_hamiltonian(0)
    with pytest.raises(ValueError, match="too small"):
        local.to_full_hamiltonian(1)


def test_local_hamiltonian_str_and_repr():
    local = LocalHamiltonian(Z, sites=[0], local_dim=2)
    text = str(local)
    rep = repr(local)
    assert "LocalHamiltonian(" in text
    assert "sites=[0]" in text
    assert "LocalHamiltonian(" in rep
    assert "local_dim=2" in rep
