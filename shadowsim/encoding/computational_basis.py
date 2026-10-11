"""Computational-basis encoding of an integer or a bit string."""

import numpy as np
import numpy.typing as npt

from shadowsim.core.state import State
from shadowsim.encoding.state_encoder import StateEncoder


class ComputationalBasisEncoding(StateEncoder):
    r"""Prepare a computational-basis state \(\lvert k\rangle\).

    An integer \(k\) in \(0 .. 2^n - 1\) becomes the one-hot vector with a 1
    at index \(k\). A length-\(n\) sequence of bits \(b_0, b_1, \ldots, b_{n-1}\)
    uses the same layout as ``tensor``: \(b_0\) is
    the most significant qubit, and

    \[
        k = \sum_{i=0}^{n-1} b_i \, 2^{n-1-i}.
    \]

    So ``[1, 0]`` on two qubits is \(\lvert 10\rangle\), index 2.

    Args:
        num_qubits: Number of qubits \(n\). Must be a non-negative integer.

    Examples:
        ```python exec="1" source="above" result="text"
        from shadowsim.encoding import ComputationalBasisEncoding

        encoder = ComputationalBasisEncoding(2)
        print(encoder.encode(2).to_numpy())
        print(encoder.encode([1, 0]).to_numpy())
        ```

    """

    def __init__(self, num_qubits: int) -> None:
        """Store the number of qubits this encoding prepares."""
        assert num_qubits >= 0, "num_qubits must be non-negative"
        assert isinstance(num_qubits, int), "num_qubits must be an integer"
        self._num_qubits = num_qubits

    def encode(self, data: npt.ArrayLike) -> State:
        r"""Return the computational-basis state for an index or a bit string.

        Args:
            data: Integer index \(k\), or a length-``num_qubits`` sequence of
                bits 0 and 1. The first bit is the most significant qubit.

        Returns:
            One-hot state \(\lvert k\rangle\).

        Raises:
            ValueError: If ``data`` is not an in-range index or a valid bit string.
        """
        index = _basis_index(self._num_qubits, data)
        vector = np.zeros(2**self._num_qubits, dtype=np.complex128)
        vector[index] = 1.0
        return State(vector, self._num_qubits)


def _basis_index(num_qubits: int, data: npt.ArrayLike) -> int:
    """Return the binary basis index encoded by ``data``."""
    if isinstance(data, (bool, np.bool_)):
        raise ValueError("basis data must be an integer index or a 1D sequence of bits 0 and 1")
    if isinstance(data, (int, np.integer)):
        return _checked_basis_index(num_qubits, int(data))

    bits = np.asarray(data)
    if bits.ndim == 0:
        if bits.dtype.kind not in "iu":
            raise ValueError("basis data must be an integer index or a 1D sequence of bits 0 and 1")
        return _checked_basis_index(num_qubits, int(bits))
    if bits.ndim != 1 or bits.shape[0] != num_qubits:
        raise ValueError(f"bit string length must equal num_qubits={num_qubits}, got shape {bits.shape}")
    if bits.dtype.kind not in "biuf":
        raise ValueError("each bit must be 0 or 1")
    if not np.all(np.isfinite(np.asarray(bits, dtype=np.float64))):
        raise ValueError("each bit must be 0 or 1")
    if not np.all((bits == 0) | (bits == 1)):
        raise ValueError("each bit must be 0 or 1")

    index = 0
    for bit in bits.tolist():
        index = (index << 1) | int(bit)
    return index


def _checked_basis_index(num_qubits: int, index: int) -> int:
    """Return ``index`` when it addresses a ``num_qubits`` Hilbert space."""
    dimension = 2**num_qubits
    if index < 0 or index >= dimension:
        raise ValueError(f"basis index must be an integer in 0 .. {dimension - 1}, got {index}")
    return index
