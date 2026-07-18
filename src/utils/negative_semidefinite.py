import numpy as np

from src.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def negative_semidefinite(matrix):
    """Return whether a matrix is negative semidefinite."""
    return np.all(_real_parts_of_eigenvalues(matrix) <= 0)
