"""Hermitian definiteness checks.

Eigenvalues with absolute value at most ``1e-10`` count as zero.
"""

import numpy as np

from shadowsim.utils.hermitian import hermitian

# Eigenvalues this close to zero count as zero.
_EIG_ATOL = 1e-10


def _real_parts_of_eigenvalues(matrix: np.ndarray) -> np.ndarray:
    """Return the real parts of the eigenvalues of ``matrix``."""
    eigvals = np.linalg.eigvals(matrix)
    return np.real_if_close(eigvals, tol=1000).real


def positive_definite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is positive definite.

    A matrix is positive definite when it is Hermitian and every eigenvalue is
    greater than ``1e-10``.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is greater
        than ``1e-10``, else ``False``.

    Examples:
        The identity is positive definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import positive_definite

        print(positive_definite(np.eye(3)))
        ```

        A zero eigenvalue makes the matrix fail the strict test:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import positive_definite

        print(positive_definite(np.diag([0.0, 1.0, 2.0])))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) > _EIG_ATOL))


def positive_semidefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is positive semidefinite.

    A matrix is positive semidefinite when it is Hermitian and every eigenvalue
    is at least ``-1e-10``.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is at least
        ``-1e-10``, else ``False``.

    Examples:
        A diagonal matrix with a zero eigenvalue is positive semidefinite but
        not positive definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import positive_semidefinite

        print(positive_semidefinite(np.diag([0.0, 1.0, 2.0])))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) >= -_EIG_ATOL))


def negative_definite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is negative definite.

    A matrix is negative definite when it is Hermitian and every eigenvalue is
    less than ``-1e-10``.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is less than
        ``-1e-10``, else ``False``.

    Examples:
        A negative multiple of the identity is negative definite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import negative_definite

        print(negative_definite(-np.eye(2)))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) < -_EIG_ATOL))


def negative_semidefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is negative semidefinite.

    A matrix is negative semidefinite when it is Hermitian and every eigenvalue
    is at most ``1e-10``.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and every eigenvalue is at most
        ``1e-10``, else ``False``.

    Examples:
        A diagonal matrix with a zero and a negative entry is negative
        semidefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import negative_semidefinite

        print(negative_semidefinite(np.diag([0.0, -1.0])))
        ```

    """
    if not hermitian(matrix):
        return False
    return bool(np.all(_real_parts_of_eigenvalues(matrix) <= _EIG_ATOL))


def indefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is indefinite.

    A matrix is indefinite when it is Hermitian and it has at least one
    eigenvalue greater than ``1e-10`` and at least one less than ``-1e-10``.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and its eigenvalues include both a
        value greater than ``1e-10`` and a value less than ``-1e-10``, else
        ``False``.

    Examples:
        Pauli \(Z\) is indefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.definiteness import indefinite

        Z = np.array([[1.0, 0.0], [0.0, -1.0]])
        print(indefinite(Z))
        ```

    """
    if not hermitian(matrix):
        return False
    eigvals = _real_parts_of_eigenvalues(matrix)
    return bool(np.any(eigvals > _EIG_ATOL) and np.any(eigvals < -_EIG_ATOL))
