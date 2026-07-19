import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def positive_definite(matrix):
    """Return whether a matrix is positive definite."""
    return np.all(_real_parts_of_eigenvalues(matrix) > 0)
