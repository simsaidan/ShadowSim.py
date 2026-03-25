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

    def multiply(self, other: PauliString) -> tuple[complex, PauliString]:
        """
        Tensor product multiplication: ``self * other = phase * result``,
        qubit-by-qubit in matching order (leftmost = qubit 0).
        """
        if len(self._paulis) != len(other._paulis):
            raise ValueError(
                f"PauliString length mismatch: {len(self._paulis)} vs {len(other._paulis)}"
            )
        phase = 1 + 0j
        out_labels: list[str] = []
        for pa, pb in zip(self._paulis, other._paulis, strict=True):
            p, lab = _multiply_labels(pa.label, pb.label)
            phase *= p
            out_labels.append(lab)
        return phase, PauliString([Pauli(ch) for ch in out_labels])

    def commutator(
        self, other: PauliString
    ) -> tuple[complex | None, PauliString | None]:
        """
        Return ``[self, other]`` as ``coeff * R`` with ``R`` a ``PauliString``,
        or ``(None, None)`` when commutators vanish.

        Uses ``P Q - Q P``: for Pauli strings this is either ``0`` or
        ``2 * (phase from P*Q) * R`` with an odd number of pairwise
        anticommuting single-qubit factors.
        """
        if len(self._paulis) != len(other._paulis):
            raise ValueError(
                f"PauliString length mismatch: {len(self._paulis)} vs {len(other._paulis)}"
            )
        m = sum(
            1
            for pa, pb in zip(self._paulis, other._paulis, strict=True)
            if _single_qubit_anticommutes(pa.label, pb.label)
        )
        if m % 2 == 0:
            return None, None
        phase_pq, res = self.multiply(other)
        return 2 * phase_pq, res
