import numpy as np


def _real_parts_of_eigenvalues(matrix):
    eigvals = np.linalg.eigvals(matrix)
    return np.real_if_close(eigvals, tol=1000).real
