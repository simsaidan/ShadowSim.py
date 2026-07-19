import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def indefinite(matrix):
    """Return whether a matrix has both positive and negative eigenvalues."""
    eigvals = _real_parts_of_eigenvalues(matrix)
    return np.any(eigvals > 0) and np.any(eigvals < 0)
