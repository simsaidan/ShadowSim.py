from __future__ import annotations
from collections.abc import Sequence
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


class PauliString:
    """
    Tensor product of single-qubit Paulis on `n` qubits.

    Indexing matches the string order: the leftmost character acts on qubit 0,
    so ``PauliString.from_string("XYZ")`` corresponds to X ⊗ Y ⊗ Z.
    """

    __slots__ = ("_paulis",)

    def __init__(self, paulis: Sequence[Pauli]):
        paulis_tuple = tuple(paulis)
        if not paulis_tuple:
            raise ValueError("PauliString must contain at least one Pauli")
        self._paulis = paulis_tuple

    @classmethod
    def from_string(cls, s: str) -> PauliString:
        s = s.strip().upper().replace(" ", "")
        if not s:
            raise ValueError("empty Pauli string")
        return cls([Pauli(ch) for ch in s])

    @property
    def paulis(self) -> tuple[Pauli, ...]:
        return self._paulis

    @property
    def num_qubits(self) -> int:
        return len(self._paulis)

    def matrix(self) -> np.ndarray:
        mats = [p.matrix() for p in self._paulis]
        out = mats[0]
        for m in mats[1:]:
            out = np.kron(out, m)
        return out

    def __len__(self) -> int:
        return len(self._paulis)

    def __str__(self) -> str:
        return "".join(p.label for p in self._paulis)

    def __repr__(self) -> str:
        inner = ", ".join(repr(p.label) for p in self._paulis)
        return f"PauliString([{inner}])"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PauliString):
            return NotImplemented
        return self._paulis == other._paulis
