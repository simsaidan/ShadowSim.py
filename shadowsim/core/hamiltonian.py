"""Hamiltonian operators."""

import numpy as np

from shadowsim.core.operator import Operator, _coerce_pauli_sum, _OperatorInput
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum
from shadowsim.utils.hermitian import hermitian


class Hamiltonian(Operator):
    """Represent a quantum Hamiltonian.

    The Hamiltonian must be Hermitian to be valid. Pauli-label / PauliSum inputs
    are accepted when all coefficients are real (no dense densification required
    to validate Hermiticity).
    """

    def __init__(self, matrix: _OperatorInput):
        """Initialize a Hamiltonian object.

        Parameter matrix: Dense Hermitian matrix, Pauli expression string,
            PauliString, or real-coefficient PauliSum.
        """
        if isinstance(matrix, np.ndarray):
            assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
            assert hermitian(matrix), "matrix must be Hermitian"
            assert matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1], "matrix must be a square 2D array"
            super().__init__(matrix)
            return

        if isinstance(matrix, (str, PauliString, PauliSum)):
            pauli_sum = _coerce_pauli_sum(matrix)
            assert pauli_sum.is_hermitian(), "matrix must be Hermitian"
            super().__init__(pauli_sum)
            return

        raise TypeError(f"matrix must be a numpy array, str, PauliString, or PauliSum; got {type(matrix)!r}")

    def __str__(self):
        """Return a string representation of the Hamiltonian."""
        if self.pauli_sum is not None and self._matrix_cache is None:
            return f"Hamiltonian(pauli_sum={self.pauli_sum})"
        return f"Hamiltonian(matrix={self.matrix})"

    def __repr__(self):
        """Return a string representation of the Hamiltonian."""
        if self.pauli_sum is not None and self._matrix_cache is None:
            return f"Hamiltonian(pauli_sum={self.pauli_sum!r})"
        return f"Hamiltonian(matrix={self.matrix})"

    def __eq__(self, other):
        """Return whether the Hamiltonian is equal to another Hamiltonian."""
        return np.allclose(self.matrix, other.matrix)

    __hash__ = None  # matrix equality uses allclose; instances are not hashable

    def __ne__(self, other):
        """Return whether the Hamiltonian is not equal to another Hamiltonian."""
        return not np.allclose(self.matrix, other.matrix)

    def to_hamiltonian_set(self):
        """Return a HamiltonianSet containing the Hamiltonian."""
        from shadowsim.core.hamiltonian_set import HamiltonianSet  # noqa: PLC0415

        return HamiltonianSet([self])

    def to_local_hamiltonian(self, local_dim: int = 2):
        """Return a LocalHamiltonian on a contiguous block of sites starting at 0.

        Parameter local_dim: The local dimension of the Hamiltonian.
        Precondition: local_dim is a positive integer.
        """
        assert isinstance(local_dim, int), "local_dim must be an integer"
        assert local_dim > 0, "local_dim must be a positive integer"

        from shadowsim.core.local_hamiltonian import LocalHamiltonian  # noqa: PLC0415

        dim = int(self.matrix.shape[0])
        n_sites = 0
        span = 1
        while span < dim:
            span *= local_dim
            n_sites += 1
        if span != dim:
            raise ValueError(f"Hamiltonian dimension {dim} is not a power of local_dim={local_dim}")
        sites = list(range(n_sites))
        lo = self.to_local_operator(sites, local_dim)
        return LocalHamiltonian(lo.matrix, lo.sites, lo.local_dim)
