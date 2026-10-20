"""Density operators (mixed quantum states)."""

from typing import Self

import numpy as np
import numpy.typing as npt

from shadowsim.core.operator import Operator, _matrices_close
from shadowsim.core.state import State
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.positive_semidefinite import positive_semidefinite


def _as_valid_density_matrix(matrix: npt.NDArray[np.complexfloating]) -> npt.NDArray[np.complexfloating]:
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

    def __init__(self, matrix: npt.NDArray[np.complexfloating]) -> None:
        """Initialize a DensityOperator.

        Parameter matrix: Dense density matrix.
        """
        if not isinstance(matrix, np.ndarray):
            raise TypeError(f"matrix must be a numpy array; got {type(matrix)!r}")
        super().__init__(_as_valid_density_matrix(matrix))

    @classmethod
    def from_state(cls, state: State) -> Self:
        """Build the pure-state projector ``|ψ⟩⟨ψ|`` from a ``State``."""
        if not isinstance(state, State):
            raise TypeError(f"state must be a State; got {type(state)!r}")
        ket = np.asarray(state.state, dtype=np.complex128).reshape(-1, 1)
        return cls(ket @ ket.conj().T)

    def trace(self) -> complex:
        """Return the trace of the density matrix."""
        return complex(np.trace(self.matrix))

    def purity(self) -> float:
        """Return the purity ``Tr(ρ²)`` as a real float.

        For a valid density operator on a ``d``-dimensional space the value
        lies in ``[1/d, 1]``: ``1`` for a pure state and ``1/d`` for the
        maximally mixed state ``I/d``. Because a density operator is
        Hermitian, this equals the squared Frobenius norm of the matrix.
        """
        return float(np.trace(self.matrix @ self.matrix).real)

    def __str__(self) -> str:
        """Return a string representation of the density operator."""
        return f"DensityOperator(matrix={self.matrix})"

    def __repr__(self) -> str:
        """Return a string representation of the density operator."""
        return f"DensityOperator(matrix={self.matrix!r})"

    def __eq__(self, other: object) -> bool:
        """Return whether the density operator equals another.

        Density operators whose matrices have different shapes compare unequal.
        """
        if not isinstance(other, DensityOperator):
            return NotImplemented
        return _matrices_close(self.matrix, other.matrix)

    __hash__ = None  # matrix equality uses allclose; instances are not hashable

    def __ne__(self, other: object) -> bool:
        """Return whether the density operator differs from another.

        Density operators whose matrices have different shapes compare unequal.
        """
        if not isinstance(other, DensityOperator):
            return NotImplemented
        return not _matrices_close(self.matrix, other.matrix)
