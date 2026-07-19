import numpy as np

from shadowsim.core.operator import Operator
from shadowsim.utils.hermitian import hermitian


class Hamiltonian(Operator):
    """
    Represents a quantum Hamiltonian.
    The Hamiltonian must be Hermitian to be valid.
    """

    def __init__(self, matrix: np.ndarray):
        """Initializes a Hamiltonian object which represents a quantum
        Hamiltonian. The Hamtonian must be Hermitian to be valid.

        Parameter matrix: The matrix representation of the Hamiltonian.
        Precondition: matrix is a numpy array.
        """
        assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
        assert hermitian(matrix), "matrix must be Hermitian"
        assert (
            matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1]
        ), "matrix must be a square 2D array"
        super().__init__(matrix)

    def __str__(self):
        """Returns a string representation of the Hamiltonian."""
        return f"Hamiltonian(matrix={self.matrix})"

    def __repr__(self):
        """Returns a string representation of the Hamiltonian."""
        return f"Hamiltonian(matrix={self.matrix})"

    def __eq__(self, other):
        """Returns whether the Hamiltonian is equal to another Hamiltonian."""
        return np.allclose(self.matrix, other.matrix)

    def __ne__(self, other):
        """Returns whether the Hamiltonian is not equal to another Hamiltonian."""
        return not np.allclose(self.matrix, other.matrix)

    def to_hamiltonian_set(self):
        """Returns a HamiltonianSet containing the Hamiltonian."""
        from shadowsim.core.hamiltonian_set import HamiltonianSet

        return HamiltonianSet([self])

    def to_local_hamiltonian(self, local_dim: int = 2):
        """Returns a LocalHamiltonian representing the Hamiltonian acting on
        the given sites.

        Parameter local_dim: The local dimension of the Hamiltonian.
        Precondition: local_dim is a positive integer.
        """
        assert isinstance(local_dim, int), "local_dim must be an integer"
        assert local_dim > 0, "local_dim must be a positive integer"

        from shadowsim.core.local_hamiltonian import LocalHamiltonian

        lo = self.to_local_operator(local_dim)
        return LocalHamiltonian(lo.matrix, lo.sites, lo.local_dim)
