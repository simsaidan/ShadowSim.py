import numpy as np

from src.core.operator_set import Operator


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


class LocalHamiltonian(Hamiltonian):
    def __init__(
        self,
        matrix: np.ndarray,
        sites: list[int],
        local_dim: int = 2,
    ):
        """
        Local Hamiltonian acting non-trivially on the provided `sites`.

        We validate that `matrix` has the expected dimension for a tensor product
        space of dimension `local_dim ** len(sites)`.
        """
        sites_list = list(sites)
        if not all(isinstance(site, int) for site in sites_list):
            raise TypeError("all `sites` entries must be integers")
        if len(set(sites_list)) != len(sites_list):
            raise ValueError("all `sites` entries must be unique")

        matrix = np.asarray(matrix)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("`matrix` must be a square 2D array")

        local_dim = int(local_dim)
        if local_dim <= 0:
            raise ValueError("`local_dim` must be a positive integer")

        expected_dim = local_dim ** len(sites_list)
        if matrix.shape[0] != expected_dim:
            raise ValueError(
                "invalid number of sites for the given matrix: "
                f"got len(sites)={len(sites_list)} and local_dim={local_dim}, "
                f"expected matrix dimension {expected_dim}x{expected_dim}, "
                f"but got {matrix.shape[0]}x{matrix.shape[1]}"
            )

        super().__init__(matrix)
        self.sites = sites_list
        self.local_dim = local_dim


class HamiltonianSet:
    def __init__(self, hamiltonians: list[Hamiltonian]):
        self.hamiltonians = hamiltonians
        self.hamiltonian_count = len(hamiltonians)
