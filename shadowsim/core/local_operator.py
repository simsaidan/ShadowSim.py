import numpy as np

from shadowsim.core.operator import Operator
from shadowsim.utils.tensor import tensor


class LocalOperator(Operator):
    """
    Represents an operator that acts non-trivially on the given `sites` of a
    tensor-product space.
    """

    def __init__(self, matrix: np.ndarray, sites: list[int], local_dim: int = 2):
        """Initializes a LocalOperator object which represents an operator that
        acts non-trivially on the given sites.

        Parameter matrix: The matrix representation of the operator.
        Precondition: matrix is a numpy array.

        Parameter sites: The sites on which the operator acts non-trivially.
        Precondition: sites is a list of contiguous integers.

        Parameter local_dim: The local dimension of the operator.
        Precondition: local_dim is a positive integer."""
        assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
        assert (
            matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1]
        ), "matrix must be a square 2D array"
        assert isinstance(sites, list), "sites must be a list"
        assert all(
            isinstance(site, int) for site in sites
        ), "all sites must be integers"
        assert len(set(sites)) == len(sites), "all sites must be unique"
        assert len(sites) >= 1, "there must be at least one site"
        assert max(sites) - min(sites) + 1 == len(
            sites
        ), """sites
        must be a contiguous range of integers"""
        assert isinstance(local_dim, int), "local_dim must be an integer"
        assert local_dim > 0, "local_dim must be a positive integer"

        expected_dim = local_dim ** len(sites)
        if matrix.shape[0] != expected_dim:
            raise ValueError(
                "invalid number of sites for the given matrix: "
                f"got len(sites)={len(sites)} and local_dim={local_dim}, "
                f"expected matrix dimension {expected_dim}x{expected_dim}, "
                f"but got {matrix.shape[0]}x{matrix.shape[1]}"
            )

        super().__init__(matrix)
        self.sites = sites
        self.local_dim = local_dim

    def get_sites(self):
        """Returns the sites on which the local operator acts non-trivially."""
        return self.sites

    def get_local_dim(self):
        """Returns the local dimension of the local operator."""
        return self.local_dim

    def get_matrix(self):
        """Returns the matrix representation of the local operator."""
        return self.matrix

    def to_operator(self):
        """Returns an Operator representing the local operator."""
        return Operator(self.matrix)

    def to_full_operator(self, total_sites: int):
        """Embed this local operator into a full system of ``total_sites``.

        The operator acts on its contiguous block ``self.sites`` and identity
        acts on all other sites.

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
        return Operator(full_matrix)

    def __str__(self):
        """Returns a string representation of the local operator."""
        return (
            "LocalOperator("
            f"sites={self.sites}, "
            f"local_dim={self.local_dim}, "
            f"shape={self.matrix.shape}"
            ")"
        )

    def __repr__(self):
        """Returns a string representation of the local operator."""
        return (
            "LocalOperator("
            f"matrix={self.matrix!r}, "
            f"sites={self.sites!r}, "
            f"local_dim={self.local_dim}"
            ")"
        )
