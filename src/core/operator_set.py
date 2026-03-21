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


class OperatorSet:
    def __init__(self, operators: list[Operator]):
        self.operators = operators
        self.operator_count = len(operators)
