"""Common interface for preparing a quantum state from classical data."""

from abc import ABC, abstractmethod

import numpy.typing as npt

from shadowsim.core.state import State


class StateEncoder(ABC):
    """Prepare a normalized :class:`~shadowsim.core.state.State` from classical data.

    Subclasses define which classical inputs they accept. Every encoding returns
    a state vector that simulators can take as ``initial_state``.
    """

    @abstractmethod
    def encode(self, data: npt.ArrayLike) -> State:
        """Return the quantum state prepared from ``data``.

        Args:
            data: Classical input for this encoding.

        Returns:
            A normalized state on the qubits this encoding uses.
        """
        raise NotImplementedError
