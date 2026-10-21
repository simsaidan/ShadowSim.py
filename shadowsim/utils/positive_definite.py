"""Positive-definite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues
from shadowsim.utils.hermitian import hermitian


def positive_definite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is positive definite.

    A matrix is positive definite when it is Hermitian and every eigenvalue is
    strictly positive.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is strictly
        positive, else ``False``.

    Examples:
        The identity is positive definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.positive_definite import positive_definite

        print(positive_definite(np.eye(3)))
        ```

        A zero eigenvalue makes the matrix fail the strict test:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.positive_definite import positive_definite

        print(positive_definite(np.diag([0.0, 1.0, 2.0])))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) > 0))
