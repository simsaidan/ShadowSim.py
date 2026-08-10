"""Tensor-product helpers."""

import numpy as np


def tensor(lst: list[np.ndarray]) -> np.ndarray:
    r"""Return the Kronecker tensor product of the arrays in ``lst``.

    Given matrices or vectors \(A_1, A_2, \ldots, A_n\), computes

    \[
        A_1 \otimes A_2 \otimes \cdots \otimes A_n
    \]

    via successive applications of :func:`numpy.kron`.

    Args:
        lst: Non-empty sequence of NumPy arrays to tensor together.

    Returns:
        The Kronecker product of the entries of ``lst``.

    Examples:
        Tensor Pauli \(Z\) with Pauli \(X\):

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.utils.tensor import tensor

        Z = np.array([[1.0, 0.0], [0.0, -1.0]])
        X = np.array([[0.0, 1.0], [1.0, 0.0]])
        print(tensor([Z, X]))
        ```

    """
    result = lst[0]
    for i in range(1, len(lst)):
        result = np.kron(result, lst[i])
    return result
