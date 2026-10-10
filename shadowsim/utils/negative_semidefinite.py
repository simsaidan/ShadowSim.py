"""Negative-semidefinite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues

# Allow tiny positive eigenvalues from floating-point noise near the boundary.
_EIG_ATOL = 1e-10


def negative_semidefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is negative semidefinite.

    A matrix is negative semidefinite when every eigenvalue has non-positive real
    part (up to a small numerical tolerance).

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if all real parts of the eigenvalues are non-positive, else ``False``.

    Examples:
        A diagonal matrix with a zero and a negative entry is negative
        semidefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.negative_semidefinite import negative_semidefinite

        print(negative_semidefinite(np.diag([0.0, -1.0])))
        ```

    """
    return np.all(_real_parts_of_eigenvalues(matrix) <= _EIG_ATOL)
