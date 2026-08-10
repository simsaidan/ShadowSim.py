"""Positive-semidefinite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def positive_semidefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is positive semidefinite.

    A matrix is positive semidefinite when every eigenvalue has non-negative real
    part.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if all real parts of the eigenvalues are non-negative, else ``False``.

    Examples:
        A diagonal matrix with a zero eigenvalue is positive semidefinite but
        not positive definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.positive_semidefinite import positive_semidefinite

        print(positive_semidefinite(np.diag([0.0, 1.0, 2.0])))
        ```

    """
    return np.all(_real_parts_of_eigenvalues(matrix) >= 0)
