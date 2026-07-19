from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from shadowsim.core.pauli import Pauli, _multiply_labels, _single_qubit_anticommutes


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
