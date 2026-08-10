"""Eigenvalue helpers for definiteness checks."""

import numpy as np


def _real_parts_of_eigenvalues(matrix):
    """Return the real parts of the eigenvalues of ``matrix``."""
    eigvals = np.linalg.eigvals(matrix)
    return np.real_if_close(eigvals, tol=1000).real
