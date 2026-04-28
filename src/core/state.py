import numpy as np


def _as_valid_state_vector(
    state: np.ndarray, num_qubits: int, local_dim: int
) -> np.ndarray:
    """Return a 1D array; raise ValueError if shape or length is invalid."""
    arr = np.asarray(state)
    if arr.ndim == 2 and (arr.shape[0] == 1 or arr.shape[1] == 1):
        arr = arr.reshape(-1)
    if arr.ndim != 1:
        raise ValueError(
            "state must be a vector (1D), not a multi-dimensional array or "
            f"full matrix; got shape {arr.shape}"
        )
    num_qubits = int(num_qubits)
    if num_qubits < 0:
        raise ValueError("`num_qubits` must be non-negative")
    local_dim = int(local_dim)
    if local_dim <= 0:
        raise ValueError("`local_dim` must be a positive integer")
    expected_len = local_dim**num_qubits
    if arr.shape[0] != expected_len:
        raise ValueError(
            "state vector length must match Hilbert space dimension "
            f"local_dim**num_qubits = {expected_len} for "
            f"num_qubits={num_qubits} and local_dim={local_dim}, "
            f"got length {arr.shape[0]}"
        )
    return arr


class State:
    def __init__(self, state: np.ndarray, num_qubits: int, local_dim: int = 2):
        assert num_qubits >= 0, "num_qubits must be non-negative"
        assert local_dim > 0, "local_dim must be a positive integer"
        self._num_qubits = int(num_qubits)
        self._local_dim = int(local_dim)
        self.state = _as_valid_state_vector(state, self._num_qubits, self._local_dim)

    def get_state(self):
        """Returns the state vector as a numpy array."""
        return self.state

    def set_state(self, state: np.ndarray):
        """Sets the state vector to a new numpy array."""
        self.state = _as_valid_state_vector(state, self._num_qubits, self._local_dim)

    def get_num_qubits(self):
        """Returns the number of qubits the state is defined on."""
        return self._num_qubits

    def get_local_dim(self):
        return self._local_dim

    def to_numpy(self):
        return self.state

    def __str__(self):
        return (
            "State("
            f"num_qubits={self._num_qubits}, "
            f"local_dim={self._local_dim}, "
            f"shape={self.state.shape}"
            ")"
        )

    def __repr__(self):
        return (
            "State("
            f"state={self.state!r}, "
            f"num_qubits={self._num_qubits}, "
            f"local_dim={self._local_dim}"
            ")"
        )
