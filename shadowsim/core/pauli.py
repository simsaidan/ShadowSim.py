from __future__ import annotations

import numpy as np


_I = np.eye(2, dtype=np.complex128)
_X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
_Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
_Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)

_PAULI_MATRICES: dict[str, np.ndarray] = {
    "I": _I,
    "X": _X,
    "Y": _Y,
    "Z": _Z,
}

_PHASES = (1, -1, 1j, -1j)


def _multiply_labels(a: str, b: str) -> tuple[complex, str]:
    """Return (phase, c) with ``a * b = phase * c`` in the Pauli group."""
    m = _PAULI_MATRICES[a] @ _PAULI_MATRICES[b]
    for c in "IXYZ":
        base = _PAULI_MATRICES[c]
        for ph in _PHASES:
            if np.allclose(m, ph * base):
                return (complex(ph), c)
    raise RuntimeError(f"unreachable: could not factor {a} @ {b}")


def _single_qubit_anticommutes(a: str, b: str) -> bool:
    return a != b and a != "I" and b != "I"


class Pauli:
    """Single-qubit Pauli operator: I, X, Y, or Z."""

    __slots__ = ("_label",)

    def __init__(self, label: str):
        label = label.upper()
        if label not in _PAULI_MATRICES:
            raise ValueError(
                f"invalid Pauli label {label!r}; expected one of I, X, Y, Z"
            )
        self._label = label

    @property
    def label(self) -> str:
        return self._label

    def matrix(self) -> np.ndarray:
        return _PAULI_MATRICES[self._label].copy()

    def __str__(self) -> str:
        return self._label

    def __repr__(self) -> str:
        return f"Pauli({self._label!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Pauli):
            return NotImplemented
        return self._label == other._label

    def multiply(self, other: Pauli) -> tuple[complex, Pauli]:
        """
        Multiply in the Pauli group: ``self * other = phase * result``,
        with ``phase`` in ``{±1, ±i}``.
        """
        phase, label = _multiply_labels(self._label, other._label)
        return phase, Pauli(label)

    def commutator(self, other: Pauli) -> tuple[complex | None, Pauli | None]:
        """
        Return ``[self, other] = self @ other - other @ self`` as ``phase * P``,
        or ``(None, None)`` when the commutator is zero.

        For single-qubit Paulis this is either ``0`` or ``2i`` times the third Pauli.
        """
        if not _single_qubit_anticommutes(self._label, other._label):
            return None, None
        phase, res = self.multiply(other)
        return 2 * phase, res
