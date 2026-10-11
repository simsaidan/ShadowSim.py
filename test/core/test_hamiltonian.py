import subprocess
import sys

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
    assert h != "not a hamiltonian"
    assert not (h == "not a hamiltonian")

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
    with pytest.raises(TypeError, match="local_dim must be an integer"):
        h.to_local_hamiltonian(local_dim=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="local_dim must be a positive integer"):
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


def test_hamiltonian_rejects_non_square_matrix():
    matrix = np.ones((2, 3), dtype=np.complex128)
    with pytest.raises(ValueError, match=r"square 2D array; got shape \(2, 3\)"):
        Hamiltonian(matrix)


def test_hamiltonian_rejects_non_hermitian_matrix():
    matrix = np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128)
    with pytest.raises(ValueError, match=r"Hermitian; got shape \(2, 2\)"):
        Hamiltonian(matrix)


def test_hamiltonian_validation_survives_without_assertions():
    script = """
import numpy as np
from shadowsim.core import Hamiltonian
matrix = np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128)
try:
    Hamiltonian(matrix)
except ValueError as exc:
    if "shape" not in str(exc):
        raise SystemExit("missing shape")
else:
    raise SystemExit("no error")
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_hamiltonian_rejects_non_hermitian_pauli_expression():
    with pytest.raises(ValueError, match=r"Hermitian; got shape \(2, 2\)"):
        Hamiltonian("1j*X")


def test_hamiltonian_rejects_unsupported_input_type():
    with pytest.raises(TypeError, match="numpy array, str, PauliString, or PauliSum"):
        Hamiltonian(1.0)  # type: ignore[arg-type]
