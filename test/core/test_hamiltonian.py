import numpy as np
import pytest

from shadowsim.core import Hamiltonian, HamiltonianSet, LocalHamiltonian, PauliString, PauliSum

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


def test_hamiltonian_from_pauli_label_and_sum():
    h = Hamiltonian("Z")
    assert h.pauli_sum is not None
    assert h._matrix_cache is None
    assert "Hamiltonian(pauli_sum=" in str(h)
    assert "Hamiltonian(pauli_sum=" in repr(h)
    assert np.allclose(h.matrix, Z)
    assert "Hamiltonian(matrix=" in str(h)

    summed = Hamiltonian("XXI + XYZ")
    assert summed.pauli_sum is not None
    assert summed.is_hermitian is True

    from_ps = Hamiltonian(PauliString.from_string("X"))
    assert from_ps.pauli_sum is not None
    from_sum = Hamiltonian(PauliSum.from_string("Y"))
    assert from_sum.pauli_sum is not None


def test_hamiltonian_rejects_non_hermitian_pauli_expression():
    with pytest.raises(AssertionError, match="Hermitian"):
        Hamiltonian("1j*X")


def test_hamiltonian_rejects_unsupported_input_type():
    with pytest.raises(TypeError, match="numpy array, str, PauliString, or PauliSum"):
        Hamiltonian(1.0)  # type: ignore[arg-type]
