"""Amplitude encoding of a classical vector into a state vector."""

import numpy as np
import numpy.typing as npt

from shadowsim.core.state import State
from shadowsim.encoding.state_encoder import StateEncoder
from shadowsim.utils.next_power_of_two import next_power_of_two


class AmplitudeEncoding(StateEncoder):
    r"""Prepare a state whose amplitudes are a normalized classical vector.

    Let \(a\) be a non-zero vector of length \(m\). It is zero-padded to length

    \[
        d = \max\left(2, 2^{\lceil \log_2 m \rceil}\right)
    \]

    and then divided by its Euclidean norm. That norm is real and non-negative,
    so the global phase of \(a\) is unchanged. The prepared state uses
    \(n = \log_2 d\) qubits, and index \(k\) of the padded vector is the
    amplitude of computational-basis state \(\lvert k\rangle\).

    Examples:
        A length-3 vector is padded to four amplitudes:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.encoding import AmplitudeEncoding

        state = AmplitudeEncoding().encode([1.0, 1.0, 0.0])
        print(state.get_num_qubits())
        print(np.round(state.to_numpy(), decimals=8))
        ```

    """

    def encode(self, data: npt.ArrayLike) -> State:
        r"""Return the normalized, zero-padded amplitude state.

        Args:
            data: Non-zero 1D vector of finite real or complex amplitudes.

        Returns:
            Normalized state on \(\log_2 d\) qubits.

        Raises:
            ValueError: If ``data`` is empty, not 1D, non-finite, or all zeros.
        """
        amplitudes = _finite_amplitudes(data)
        # Scale by the largest magnitude first. A direct L2 norm underflows when
        # every amplitude is far below 1, and the result is then not normalized.
        scale = float(np.max(np.abs(amplitudes)))
        if scale == 0.0:
            raise ValueError("amplitude vector must be non-zero")
        scaled = amplitudes / scale

        padded_length = max(2, next_power_of_two(int(amplitudes.shape[0])))
        padded = np.zeros(padded_length, dtype=np.complex128)
        padded[: scaled.shape[0]] = scaled
        padded /= np.linalg.norm(scaled)
        return State(padded, padded_length.bit_length() - 1)


def _finite_amplitudes(data: npt.ArrayLike) -> npt.NDArray[np.complex128]:
    """Return ``data`` as a non-empty 1D array of finite complex amplitudes."""
    amplitudes = np.asarray(data)
    if amplitudes.dtype.kind not in "biufc":
        raise ValueError("amplitudes must be a non-empty 1D array of finite numbers")
    if amplitudes.ndim != 1 or amplitudes.shape[0] == 0:
        raise ValueError("amplitudes must be a non-empty 1D array of finite numbers")
    amplitudes = np.asarray(amplitudes, dtype=np.complex128)
    if not np.all(np.isfinite(amplitudes)):
        raise ValueError("amplitudes must be a non-empty 1D array of finite numbers")
    return amplitudes
