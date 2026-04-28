import numpy as np


def _as_valid_state_vector(
    state: np.ndarray, num_qubits: int, local_dim: int
) -> np.ndarray:
    """
    Checks whether a state vector is valid or not. If it is valid, returns
    the state vector. If it is not valid, raises a ValueError.

    A state vector is valid if it is a 1D numpy array, has the correct length,
    and is normalized.

    Parameter state: The state vector to check.
    Precondition: state is a numpy array.

    Parameter num_qubits: The number of qubits the state is defined on.
    Precondition: num_qubits is a non-negative integer.

    Parameter local_dim: The local dimension of the state.
    Precondition: local_dim is a positive integer.
    """

    arr = np.asarray(state)
    if arr.ndim == 2 and (arr.shape[0] == 1 or arr.shape[1] == 1):
        arr = arr.reshape(-1)
    if arr.ndim != 1:
        raise ValueError(
            "state must be a vector (1D), not a multi-dimensional array or "
            f"full matrix; got shape {arr.shape}"
        )
    expected_len = local_dim**num_qubits
    if arr.shape[0] != expected_len:
        raise ValueError(
            "state vector length must match Hilbert space dimension "
            f"local_dim**num_qubits = {expected_len} for "
            f"num_qubits={num_qubits} and local_dim={local_dim}, "
            f"got length {arr.shape[0]}"
        )
    norm = np.linalg.norm(arr)
    if not np.isclose(norm, 1.0):
        raise ValueError(f"state vector must be normalized (||state||=1), got {norm}")
    return arr


class State:
    def __init__(self, state: np.ndarray, num_qubits: int, local_dim: int = 2):
        """Initializes a State object which represents a quantum state.

        Parameter state: The state vector to initialize the state with.
        Precondition: state is a numpy array.

        Parameter num_qubits: The number of qubits the state is defined on.
        Precondition: num_qubits is a non-negative integer.

        Parameter local_dim: The local dimension of the state.
        Precondition: local_dim is a positive integer.
        """
        assert num_qubits >= 0, "num_qubits must be non-negative"
        assert isinstance(num_qubits, int), "num_qubits must be an integer"
        assert local_dim > 0, "local_dim must be a positive integer"
        assert isinstance(local_dim, int), "local_dim must be an integer"
        self._num_qubits = num_qubits
        self._local_dim = local_dim
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
        """Returns the local dimension of the state."""
        return self._local_dim

    def to_numpy(self):
        """Returns the state vector as a numpy array."""
        return self.state

    def __str__(self):
        """Returns a string representation of the state."""
        return (
            "State("
            f"num_qubits={self._num_qubits}, "
            f"local_dim={self._local_dim}, "
            f"shape={self.state.shape}"
            ")"
        )

    def __repr__(self):
        """Returns a string representation of the state."""
        return (
            "State("
            f"state={self.state!r}, "
            f"num_qubits={self._num_qubits}, "
            f"local_dim={self._local_dim}"
            ")"
        )
