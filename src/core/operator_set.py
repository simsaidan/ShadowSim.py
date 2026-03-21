import numpy as np


class Operator:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix
        self.dimension = matrix.shape[0]
        self.is_hermitian = np.allclose(matrix, matrix.conj().T)
        self.is_unitary = np.allclose(matrix @ matrix.conj().T, np.eye(self.dimension))
        self.is_positive_semidefinite = np.all(np.linalg.eigvals(matrix) >= 0)
        self.is_negative_semidefinite = np.all(np.linalg.eigvals(matrix) <= 0)
        self.is_indefinite = np.any(np.linalg.eigvals(matrix) > 0) and np.any(
            np.linalg.eigvals(matrix) < 0
        )

        def is_hermitian(self):
            return np.allclose(self.matrix, self.matrix.conj().T)

        def is_unitary(self):
            return np.allclose(
                self.matrix @ self.matrix.conj().T, np.eye(self.dimension)
            )

        def is_positive_semidefinite(self):
            return np.all(np.linalg.eigvals(self.matrix) >= 0)

        def is_negative_semidefinite(self):
            return np.all(np.linalg.eigvals(self.matrix) <= 0)

        def is_indefinite(self):
            return np.any(np.linalg.eigvals(self.matrix) > 0) and np.any(
                np.linalg.eigvals(self.matrix) < 0
            )

    def __str__(self):
        return f"Operator(matrix={self.matrix})"

    def __repr__(self):
        return f"Operator(matrix={self.matrix})"

    def __eq__(self, other):
        return np.allclose(self.matrix, other.matrix)

    def __ne__(self, other):
        return not np.allclose(self.matrix, other.matrix)

    def to_operator_set(self):
        return OperatorSet([self])


class LocalOperator(Operator):
    """
    Operator acting non-trivially on the given `sites` of a tensor-product space.

    ``sites`` must be distinct integers forming a single contiguous block (e.g.
    ``[1, 2, 3]`` or ``[3, 2, 1]``); gaps are not supported yet.

    The `matrix` dimension must match ``local_dim ** len(sites)``.
    """

    def __init__(
        self,
        matrix: np.ndarray,
        sites: list[int],
        local_dim: int = 2,
    ):
        sites_list = list(sites)
        if not all(isinstance(site, int) for site in sites_list):
            raise TypeError("all `sites` entries must be integers")
        if len(set(sites_list)) != len(sites_list):
            raise ValueError("all `sites` entries must be unique")
        if len(sites_list) > 1:
            lo, hi = min(sites_list), max(sites_list)
            if hi - lo + 1 != len(sites_list):
                raise ValueError(
                    "non-consecutive site indices are not supported yet; "
                    "`sites` must be a contiguous range of integers (e.g. "
                    "`[0, 1, 2]`). "
                    f"Got {sites_list!r}."
                )

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


class OperatorSet:
    def __init__(self, operators: list[Operator]):
        self.operators = operators
        self.operator_count = len(operators)
