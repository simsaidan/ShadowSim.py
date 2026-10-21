"""Negative-semidefinite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues
from shadowsim.utils.hermitian import hermitian

# Allow tiny positive eigenvalues from floating-point noise near the boundary.
_EIG_ATOL = 1e-10


def negative_semidefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is negative semidefinite.

    A matrix is negative semidefinite when it is Hermitian and every eigenvalue
    is non-positive (up to a small numerical tolerance).

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is non-positive,
        else ``False``.

    Examples:
        A diagonal matrix with a zero and a negative entry is negative
        semidefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.negative_semidefinite import negative_semidefinite

        print(negative_semidefinite(np.diag([0.0, -1.0])))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) <= _EIG_ATOL))
