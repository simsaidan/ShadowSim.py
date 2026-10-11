"""Binary-reflected Gray encoding of an integer or a bit string."""

import numpy as np
import numpy.typing as npt

from shadowsim.core.state import State
from shadowsim.encoding.computational_basis import _basis_index
from shadowsim.encoding.state_encoder import StateEncoder


class GrayEncoding(StateEncoder):
    r"""Prepare the computational-basis state at the Gray code of \(k\).

    An integer \(k\) in \(0 .. 2^n - 1\), or a length-\(n\) bit string read as
    that integer with the first bit most significant, is mapped by the
    binary-reflected Gray code

    \[
        g(k) = k \oplus (k \gg 1).
    \]

    The prepared state is the one-hot vector with a 1 at index \(g(k)\).
    Consecutive integers therefore land on basis states at Hamming distance 1.

    On two qubits, \(k = 0, 1, 2, 3\) prepares
    \(\lvert 00\rangle, \lvert 01\rangle, \lvert 11\rangle, \lvert 10\rangle\).
    So ``[1, 0]`` is the binary integer 2 and prepares \(\lvert 11\rangle\).

    Args:
        num_qubits: Number of qubits \(n\). Must be a non-negative integer.

    Examples:
        ```python exec="1" source="above" result="text"
        from shadowsim.encoding import GrayEncoding

        encoder = GrayEncoding(2)
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
        r"""Return the Gray-labeled computational-basis state for an index or a bit string.

        Args:
            data: Integer index \(k\), or a length-``num_qubits`` sequence of
                bits 0 and 1. The first bit is the most significant qubit, and
                the sequence is read as a standard binary integer.

        Returns:
            One-hot state \(\lvert g(k)\rangle\), where \(g(k) = k \oplus (k \gg 1)\).

        Raises:
            ValueError: If ``data`` is not an in-range index or a valid bit string.
        """
        index = _basis_index(self._num_qubits, data)
        gray = index ^ (index >> 1)
        vector = np.zeros(2**self._num_qubits, dtype=np.complex128)
        vector[gray] = 1.0
        return State(vector, self._num_qubits)
