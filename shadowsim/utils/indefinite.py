"""Indefinite matrix checks."""

import numpy as np

from shadowsim.utils._real_parts_of_eigenvalues import _real_parts_of_eigenvalues


def indefinite(matrix: np.ndarray) -> bool:
    r"""Return whether a matrix is indefinite.

    A matrix is indefinite when it has at least one eigenvalue with positive real
    part and at least one with negative real part.

    Args:
        matrix: Square matrix to check.

    Returns:
        ``True`` if the matrix has both positive and negative eigenvalue real
        parts, else ``False``.

    Examples:
        Pauli \(Z\) is indefinite:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.indefinite import indefinite

        Z = np.array([[1.0, 0.0], [0.0, -1.0]])
        print(indefinite(Z))
        ```

    """
    eigvals = _real_parts_of_eigenvalues(matrix)
    return np.any(eigvals > 0) and np.any(eigvals < 0)
