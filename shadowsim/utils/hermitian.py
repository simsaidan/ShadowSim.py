"""Hermitian-matrix checks."""

import numpy as np


def hermitian(H: np.ndarray) -> bool:
    r"""Return whether the NumPy matrix ``H`` is Hermitian.

    A square matrix \(H\) is Hermitian when it equals its conjugate transpose,
    \(H = H^\dagger\).

    Args:
        H: Square complex matrix.

    Returns:
        ``True`` if ``H`` is Hermitian up to numerical tolerance, else ``False``.

    Examples:
        The Pauli \(Y\) matrix is Hermitian:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.hermitian import hermitian

        Y = np.array([[0.0, -1j], [1j, 0.0]])
        print(hermitian(Y))
        ```

        A non-symmetric complex matrix is not:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.hermitian import hermitian

        print(hermitian(np.array([[1.0 + 2j, 0.0], [0.0, 0.0]])))
        ```

    """
    return np.allclose(H, H.conjugate().T)
