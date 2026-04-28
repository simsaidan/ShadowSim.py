import numpy as np

from src.core.utils import (
    hermitian,
    indefinite,
    negative_semidefinite,
    positive_semidefinite,
    tensor,
    unitary,
)


class Operator:
    def __init__(self, matrix: np.ndarray, name: str = None):
        """Initializes an Operator object which represents a quantum operator.

        Parameter matrix: The matrix representation of the operator.
        Precondition: matrix is a numpy array.

        Parameter name: The name of the operator.
        Precondition: name is a string or None.
        """
        assert isinstance(matrix, np.ndarray), "matrix must be a numpy array"
        assert isinstance(name, str) or name is None, "name must be a string or None"
        self.matrix = matrix
        self.name = name
        self.dimension = matrix.shape[0]
        self.is_hermitian = hermitian(matrix)
        self.is_unitary = unitary(matrix)
        self.is_positive_semidefinite = positive_semidefinite(matrix)
        self.is_negative_semidefinite = negative_semidefinite(matrix)
        self.is_indefinite = indefinite(matrix)

    def is_hermitian(self):
        """Returns whether the operator is Hermitian."""
        return hermitian(self.matrix)

    def is_unitary(self):
        """Returns whether the operator is unitary."""
        return unitary(self.matrix)

    def is_positive_semidefinite(self):
        """Returns whether the operator is positive semidefinite."""
        return positive_semidefinite(self.matrix)

    def is_negative_semidefinite(self):
        """Returns whether the operator is negative semidefinite."""
        return negative_semidefinite(self.matrix)

    def is_indefinite(self):
        """Returns whether the operator is indefinite."""
        return indefinite(self.matrix)

    def __str__(self):
        """Returns a string representation of the operator."""
        return f"Operator(matrix={self.matrix})"

    def __repr__(self):
        """Returns a string representation of the operator."""
        return f"Operator(matrix={self.matrix})"

    def __eq__(self, other):
        """Returns whether the operator is equal to another operator."""
        return np.allclose(self.matrix, other.matrix)

    def __ne__(self, other):
        """Returns whether the operator is not equal to another operator."""
        return not np.allclose(self.matrix, other.matrix)

    def to_operator_set(self):
        """Returns an OperatorSet containing the operator."""
        return OperatorSet([self])

    def to_local_operator(self, sites: list[int], local_dim: int = 2):
        """Returns a LocalOperator representing the operator acting on the given sites."""
        return LocalOperator(self.matrix, sites, local_dim)

    def set_name(self, name: str | None):
        """Sets the operator name."""
        assert isinstance(name, str) or name is None, "name must be a string or None"
        self.name = name


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


class OperatorSet:
    def __init__(self, operators: list[Operator]):
        """Initializes an OperatorSet object which represents a set of quantum operators.

        Parameter operators: The list of operators to initialize the operator set with.
        Precondition: operators is a list of Operator objects.
        """
        assert isinstance(operators, list), "operators must be a list"
        assert all(
            isinstance(op, Operator) for op in operators
        ), "all operators must be Operator objects"
        self.operators = operators
        self.operator_count = len(operators)

    def __iter__(self):
        """Returns an iterator over the operators in the operator set."""
        return iter(self.operators)

    def __len__(self):
        """Returns the number of operators in the operator set."""
        return len(self.operators)

    def __getitem__(self, index: int):
        """Returns the operator at the given index."""
        assert isinstance(index, int), "index must be an integer"
        assert (
            index >= 0 and index < self.operator_count
        ), "index must be within the range of the operator set"
        return self.operators[index]

    def __str__(self):
        """Returns a string representation of the operator set."""
        return f"OperatorSet(operator_count={self.operator_count})"

    def __repr__(self):
        """Returns a string representation of the operator set."""
        return f"OperatorSet(operators={self.operators!r})"
