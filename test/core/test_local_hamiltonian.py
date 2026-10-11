import numpy as np
import pytest

from shadowsim.core import Hamiltonian, LocalHamiltonian

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
    with pytest.raises(TypeError, match="total_sites must be an integer"):
        local.to_full_hamiltonian(3.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="total_sites must be positive"):
        local.to_full_hamiltonian(0)
    with pytest.raises(ValueError, match="too small"):
        local.to_full_hamiltonian(1)
    negative = LocalHamiltonian(Z, sites=[-1], local_dim=2)
    with pytest.raises(ValueError, match=r"non-negative; got \[-1\]"):
        negative.to_full_hamiltonian(1)


def test_local_hamiltonian_rejects_bad_matrix_and_sites():
    with pytest.raises(ValueError, match=r"Hermitian; got shape \(2, 2\)"):
        LocalHamiltonian(np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128), sites=[0])
    with pytest.raises(ValueError, match=r"square 2D array; got shape \(1, 3\)"):
        LocalHamiltonian(np.ones((1, 3), dtype=np.complex128), sites=[0])
    with pytest.raises(ValueError, match=r"all sites must be unique; got \[0, 0\]"):
        LocalHamiltonian(np.eye(4), sites=[0, 0], local_dim=2)
    with pytest.raises(ValueError, match=r"contiguous range of integers; got \[0, 2\]"):
        LocalHamiltonian(np.eye(4), sites=[0, 2], local_dim=2)
    with pytest.raises(TypeError, match="numpy array"):
        LocalHamiltonian([[1.0, 0.0], [0.0, 1.0]], sites=[0])  # type: ignore[arg-type]


def test_local_hamiltonian_str_and_repr():
    local = LocalHamiltonian(Z, sites=[0], local_dim=2)
    text = str(local)
    rep = repr(local)
    assert "LocalHamiltonian(" in text
    assert "sites=[0]" in text
    assert "LocalHamiltonian(" in rep
    assert "local_dim=2" in rep
