import numpy as np
import pytest

from shadowsim.core import Hamiltonian
from shadowsim.core import HamiltonianSet
from shadowsim.core import LocalHamiltonian


Z = np.diag([1.0, -1.0]).astype(np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def test_hamiltonian_str_repr_equality_and_conversions():
    h = Hamiltonian(Z)
    other = Hamiltonian(Z)
    different = Hamiltonian(X)

    assert "Hamiltonian(matrix=" in str(h)
    assert "Hamiltonian(matrix=" in repr(h)
    assert h == other
    assert h != different

    h_set = h.to_hamiltonian_set()
    assert isinstance(h_set, HamiltonianSet)
    assert len(h_set) == 1
    assert h_set[0] == h

    local = h.to_local_hamiltonian(local_dim=2)
    assert isinstance(local, LocalHamiltonian)
    assert local.sites == [0]
    assert local.local_dim == 2
    assert np.allclose(local.matrix, Z)


def test_hamiltonian_to_local_hamiltonian_validates_local_dim():
    h = Hamiltonian(Z)
    with pytest.raises(AssertionError, match="local_dim must be an integer"):
        h.to_local_hamiltonian(local_dim=2.0)  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match="local_dim must be a positive integer"):
        h.to_local_hamiltonian(local_dim=0)
    with pytest.raises(ValueError, match="not a power of local_dim"):
        Hamiltonian(np.eye(3, dtype=np.complex128)).to_local_hamiltonian(local_dim=2)
