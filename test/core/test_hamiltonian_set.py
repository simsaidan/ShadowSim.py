import numpy as np
import pytest

from shadowsim.core import Hamiltonian, HamiltonianSet

Z = np.diag([1.0, -1.0]).astype(np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def test_hamiltonian_set_protocols_and_repr():
    h1 = Hamiltonian(Z)
    h2 = Hamiltonian(X)
    h_set = HamiltonianSet([h1, h2])

    assert h_set.hamiltonian_count == 2
    assert len(h_set) == 2
    assert list(h_set) == [h1, h2]
    assert h_set[0] == h1
    assert h1 in h_set
    assert Hamiltonian(np.eye(2, dtype=np.complex128)) not in h_set
    assert "HamiltonianSet(hamiltonian_count=2)" == str(h_set)
    assert "HamiltonianSet(hamiltonians=" in repr(h_set)


def test_hamiltonian_set_validates_inputs():
    with pytest.raises(AssertionError, match="hamiltonians must be a list"):
        HamiltonianSet(Hamiltonian(Z))  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match="all hamiltonians must be Hamiltonian"):
        HamiltonianSet([Hamiltonian(Z), 123])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="expected Pauli word|invalid Pauli"):
        HamiltonianSet([Hamiltonian(Z), "nope"])


def test_hamiltonian_set_coerces_pauli_labels():
    h_set = HamiltonianSet(["Z", "XXI + XYZ"])
    assert len(h_set) == 2
    assert h_set[0].name == "Z"
    assert h_set[1].pauli_sum is not None
