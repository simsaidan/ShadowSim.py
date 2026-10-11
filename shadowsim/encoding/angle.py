"""Angle encoding as a product of single-qubit Y rotations."""

import numpy as np
import numpy.typing as npt

from shadowsim.core.state import State
from shadowsim.encoding.state_encoder import StateEncoder
from shadowsim.utils.tensor import tensor


class AngleEncoding(StateEncoder):
    r"""Prepare \(\bigotimes_i R_y(\theta_i)\lvert 0\rangle\) from one angle per qubit.

    Each angle is a rotation in radians. On a single qubit,

    \[
        R_y(\theta)\lvert 0\rangle = \cos(\theta/2)\lvert 0\rangle + \sin(\theta/2)\lvert 1\rangle.
    \]

    Angles are not amplitudes: they are not normalized. The first angle is the
    first factor of :func:`shadowsim.utils.tensor.tensor`, so it is the most
    significant qubit. The number of qubits is the length of ``data``.

    Examples:
        A \(\pi/2\) rotation prepares the equal superposition:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.encoding import AngleEncoding

        state = AngleEncoding().encode([np.pi / 2])
        print(np.round(state.to_numpy(), decimals=8))
        ```

    """

    def encode(self, data: npt.ArrayLike) -> State:
        """Return the product state for one Y rotation per qubit.

        Args:
            data: One finite real angle, in radians, per qubit.

        Returns:
            Normalized product state on ``len(data)`` qubits.

        Raises:
            ValueError: If ``data`` is not a non-empty 1D array of finite real numbers.
        """
        angles = _real_angles(data)
        kets = [np.array([np.cos(0.5 * theta), np.sin(0.5 * theta)], dtype=np.complex128) for theta in angles]
        vector = tensor(kets)
        vector = vector / np.linalg.norm(vector)
        return State(vector, int(angles.shape[0]))


def _real_angles(data: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Return ``data`` as a non-empty 1D array of finite real angles."""
    angles = np.asarray(data)
    if angles.dtype.kind not in "biuf" or not np.isrealobj(angles):
        raise ValueError("angles must be a non-empty 1D array of finite real numbers")
    if angles.ndim != 1 or angles.shape[0] == 0:
        raise ValueError("angles must be a non-empty 1D array of finite real numbers")
    angles = np.asarray(angles, dtype=np.float64)
    if not np.all(np.isfinite(angles)):
        raise ValueError("angles must be a non-empty 1D array of finite real numbers")
    return angles
