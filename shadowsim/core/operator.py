import numpy as np

from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.indefinite import indefinite
from shadowsim.utils.negative_semidefinite import negative_semidefinite
from shadowsim.utils.positive_semidefinite import positive_semidefinite
from shadowsim.utils.unitary import unitary


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
        from shadowsim.core.operator_set import OperatorSet

        return OperatorSet([self])

    def to_local_operator(self, sites: list[int], local_dim: int = 2):
        """Returns a LocalOperator representing the operator acting on the given sites."""
        from shadowsim.core.local_operator import LocalOperator

        return LocalOperator(self.matrix, sites, local_dim)

    def set_name(self, name: str | None):
        """Sets the operator name."""
        assert isinstance(name, str) or name is None, "name must be a string or None"
        self.name = name
