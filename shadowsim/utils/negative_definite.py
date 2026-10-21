"""Negative-definite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues
from shadowsim.utils.hermitian import hermitian


def negative_definite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is negative definite.

    A matrix is negative definite when it is Hermitian and every eigenvalue is
    strictly negative.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is strictly
        negative, else ``False``.

    Examples:
        A negative multiple of the identity is negative definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.negative_definite import negative_definite

        print(negative_definite(-np.eye(2)))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) < 0))
