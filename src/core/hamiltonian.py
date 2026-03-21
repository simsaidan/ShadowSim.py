import numpy as np

from src.core.operator_set import LocalOperator, Operator


class Hamiltonian(Operator):
    def __init__(self, matrix: np.ndarray):
        super().__init__(matrix)

    def __str__(self):
        return f"Hamiltonian(matrix={self.matrix})"

    def __repr__(self):
        return f"Hamiltonian(matrix={self.matrix})"

    def __eq__(self, other):
        return np.allclose(self.matrix, other.matrix)

    def __ne__(self, other):
        return not np.allclose(self.matrix, other.matrix)

    def to_hamiltonian_set(self):
        return HamiltonianSet([self])


class LocalHamiltonian(LocalOperator, Hamiltonian):
    """
    Local Hamiltonian acting non-trivially on the provided `sites`.

    ``sites`` must be distinct consecutive integers; see `LocalOperator`.
    """

    def __init__(
        self,
        matrix: np.ndarray,
        sites: list[int],
        local_dim: int = 2,
    ):
        super().__init__(matrix, sites, local_dim)


class HamiltonianSet:
    def __init__(self, hamiltonians: list[Hamiltonian]):
        self.hamiltonians = hamiltonians
        self.hamiltonian_count = len(hamiltonians)
