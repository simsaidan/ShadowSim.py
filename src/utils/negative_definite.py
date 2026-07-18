import numpy as np

from src.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def negative_definite(matrix):
    """Return whether a matrix is negative definite."""
    return np.all(_real_parts_of_eigenvalues(matrix) < 0)
