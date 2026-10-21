"""Indefinite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues
from shadowsim.utils.hermitian import hermitian


def indefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is indefinite.

    A matrix is indefinite when it is Hermitian and it has at least one positive
    eigenvalue and at least one negative eigenvalue.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix is Hermitian and its eigenvalues include both a
        positive and a negative value, else ``False``.

    Examples:
        Pauli \(Z\) is indefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.indefinite import indefinite

        Z = np.array([[1.0, 0.0], [0.0, -1.0]])
        print(indefinite(Z))
        ```

    """
    if not hermitian(matrix):
        return False
    eigvals = _real_parts_of_eigenvalues(matrix)
    return bool(np.any(eigvals > 0) and np.any(eigvals < 0))
