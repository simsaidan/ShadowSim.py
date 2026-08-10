"""Unitary-matrix checks."""

import numpy as np


def unitary(U: np.ndarray) -> bool:
    r"""Return whether the NumPy matrix ``U`` is unitary.

    A square matrix \(U\) is unitary when \(U U^\dagger = I\).

    Args:
        U: Square complex matrix.

    Returns:
        ``True`` if ``U`` is unitary up to numerical tolerance, else ``False``.

    Examples:
        The 2-qubit Hadamard gate is unitary:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.unitary import unitary

        H = np.array([[1.0, 1.0], [1.0, -1.0]]) / np.sqrt(2)
        print(unitary(H))
        ```

        A shear matrix is not:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.unitary import unitary

        print(unitary(np.array([[1.0, 2.0], [0.0, 1.0]])))
        ```

    """
    return np.allclose(np.eye(U.shape[0]), np.dot(U, U.conjugate().T))
