"""Density operators (mixed quantum states)."""

import numpy as np

from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.positive_semidefinite import positive_semidefinite


def _as_valid_density_matrix(matrix: np.ndarray) -> np.ndarray:
    """Validate a density matrix and return it as a complex ndarray."""
    arr = np.asarray(matrix, dtype=np.complex128)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise ValueError(f"density matrix must be a square 2D array; got shape {arr.shape}")
    if not hermitian(arr):
        raise ValueError("density matrix must be Hermitian")
    if not positive_semidefinite(arr):
        raise ValueError("density matrix must be positive semidefinite")
    tr = np.trace(arr)
    if not np.isclose(tr, 1.0):
        raise ValueError(f"density matrix must have trace 1, got {tr}")
    return arr


class DensityOperator(Operator):
    """Represent a density operator (mixed quantum state).

    The matrix must be square, Hermitian, positive semidefinite, and unit-trace.
    """

    def __init__(self, matrix: np.ndarray):
        """Initialize a DensityOperator.

        Parameter matrix: Dense density matrix.
        """
        if not isinstance(matrix, np.ndarray):
            raise TypeError(f"matrix must be a numpy array; got {type(matrix)!r}")
        super().__init__(_as_valid_density_matrix(matrix))

    @classmethod
    def from_state(cls, state: State) -> "DensityOperator":
        """Build the pure-state projector ``|ψ⟩⟨ψ|`` from a :class:`State`."""
        if not isinstance(state, State):
            raise TypeError(f"state must be a State; got {type(state)!r}")
        ket = np.asarray(state.state, dtype=np.complex128).reshape(-1, 1)
        return cls(ket @ ket.conj().T)

    def trace(self) -> complex:
        """Return the trace of the density matrix."""
        return complex(np.trace(self.matrix))

    def __str__(self):
        """Return a string representation of the density operator."""
        return f"DensityOperator(matrix={self.matrix})"

    def __repr__(self):
        """Return a string representation of the density operator."""
        return f"DensityOperator(matrix={self.matrix!r})"

    def __eq__(self, other):
        """Return whether the density operator equals another."""
        return np.allclose(self.matrix, other.matrix)

    __hash__ = None  # matrix equality uses allclose; instances are not hashable

    def __ne__(self, other):
        """Return whether the density operator differs from another."""
        return not np.allclose(self.matrix, other.matrix)
