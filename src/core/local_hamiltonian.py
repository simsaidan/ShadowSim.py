import numpy as np

from src.core.hamiltonian import Hamiltonian
from src.core.local_operator import LocalOperator
from src.utils.hermitian import hermitian
from src.utils.tensor import tensor


class LocalHamiltonian(LocalOperator, Hamiltonian):
    """
    Local Hamiltonian acting non-trivially on the provided sites.

    ``sites`` must be distinct consecutive integers; see `LocalOperator`.
    """

    def __init__(
        self,
        matrix: np.ndarray,
        sites: list[int],
        local_dim: int = 2,
    ):
        assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
        assert (
            matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1]
        ), "matrix must be a square 2D array"
        assert hermitian(matrix), "matrix must be Hermitian"
        assert isinstance(sites, list), "sites must be a list"
        assert all(
            isinstance(site, int) for site in sites
        ), "all sites must be integers"
        assert len(set(sites)) == len(sites), "all sites must be unique"
        assert len(sites) >= 1, "there must be at least one site"
        assert max(sites) - min(sites) + 1 == len(
            sites
        ), "sites must be a contiguous range of integers"
        assert isinstance(local_dim, int), "local_dim must be an integer"
        assert local_dim > 0, "local_dim must be a positive integer"
        super().__init__(matrix, sites, local_dim)

    def to_full_hamiltonian(self, total_sites: int):
        """Returns a FullHamiltonian representing the local Hamiltonian acting on
        the given sites.

        Parameter total_sites: The total number of sites in the full system.
        Precondition: total_sites is a positive integer.
        """
        assert isinstance(total_sites, int), "total_sites must be an integer"
        assert total_sites >= 1, "total_sites must be positive"

        lo, hi = min(self.sites), max(self.sites)
        assert lo >= 0, "site indices must be non-negative"
        if hi >= total_sites:
            raise ValueError(
                f"total_sites={total_sites} is too small for local sites {self.sites}"
            )

        eye = np.eye(self.local_dim, dtype=self.matrix.dtype)
        left_id = [eye] * lo
        right_id = [eye] * (total_sites - hi - 1)
        full_matrix = tensor(left_id + [self.matrix] + right_id)
        return Hamiltonian(full_matrix)

    def get_sites(self):
        """Returns the sites on which the local Hamiltonian acts non-trivially."""
        return self.sites

    def get_local_dim(self):
        """Returns the local dimension of the local Hamiltonian."""
        return self.local_dim

    def get_matrix(self):
        """Returns the matrix representation of the local Hamiltonian."""
        return self.matrix

    def __str__(self):
        """Returns a string representation of the LocalHamiltonian."""
        return (
            "LocalHamiltonian("
            f"sites={self.sites}, "
            f"local_dim={self.local_dim}, "
            f"shape={self.matrix.shape}"
            ")"
        )

    def __repr__(self):
        """Returns a string representation of the LocalHamiltonian."""
        return (
            "LocalHamiltonian("
            f"matrix={self.matrix!r}, "
            f"sites={self.sites!r}, "
            f"local_dim={self.local_dim}"
            ")"
        )
