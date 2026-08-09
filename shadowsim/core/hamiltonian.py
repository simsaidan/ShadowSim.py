"""Hamiltonian operators."""

import numpy as np

from shadowsim.core.operator import Operator
from shadowsim.utils.hermitian import hermitian


class Hamiltonian(Operator):
    """Represent a quantum Hamiltonian.

    The Hamiltonian must be Hermitian to be valid.
    """

    def __init__(self, matrix: np.ndarray):
        """Initialize a Hamiltonian object.

        The Hamiltonian must be Hermitian to be valid.

        Parameter matrix: The matrix representation of the Hamiltonian.
        Precondition: matrix is a numpy array.
        """
        assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
        assert hermitian(matrix), "matrix must be Hermitian"
        assert matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1], "matrix must be a square 2D array"
        super().__init__(matrix)

    def __str__(self):
        """Return a string representation of the Hamiltonian."""
        return f"Hamiltonian(matrix={self.matrix})"

    def __repr__(self):
        """Return a string representation of the Hamiltonian."""
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
