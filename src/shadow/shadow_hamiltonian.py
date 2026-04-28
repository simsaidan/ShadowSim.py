from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from itertools import product

import numpy as np

from src.core.hamiltonian import (
    Hamiltonian,
    LocalHamiltonian,
    combined_hamiltonian_matrix,
)
from src.core.operator_set import OperatorSet
from src.core.pauli import PauliString
from src.core.utils import hermitian, unitary


def _infer_num_qubits(terms: list[Hamiltonian]) -> int:
    """
    Infer ``num_qubits`` from full-domain terms. All such terms must share the
    same matrix dimension ``2**n`` (assumed here).
    """
    d_ref: int | None = None
    for h in terms:
        if isinstance(h, LocalHamiltonian):
            continue
        d = int(np.asarray(h.matrix).shape[0])
        if d <= 0 or (d & (d - 1)) != 0:
            raise ValueError(
                "full-domain Hamiltonian matrix dimension must be a power of 2, "
                f"got {d}"
            )
        if d_ref is None:
            d_ref = d
        elif d != d_ref:
            raise ValueError(
                "all full-domain Hamiltonian terms must have the same matrix size; "
                f"expected {d_ref}x{d_ref}, got {d}x{d}"
            )
    if d_ref is None:
        raise ValueError(
            "pass num_qubits= when all terms are LocalHamiltonian; otherwise "
            "include at least one full-domain Hamiltonian to infer qubit count."
        )
    return d_ref.bit_length() - 1


class ShadowHamiltonian:
    """
    There are two matrices:

    - ``self.H``: the **input** model on the full qubit space, always ``(2^n, 2^n)``,
      because you represent Pauli operators in that space. It is *not* “the
      shadow Hamiltonian” in the sense of the construction; it is just what
      you passed in, summed.
    - ``self.H_S`` (also ``.shadow`` / ``get_H_S()``): the **actual shadow
      object**—commutator matrix in the **closed Pauli label basis** only, shape
      **``(m, m)``** with **``m = |closure|``**. That size does **not** have to
      equal ``2^n``; it is whatever the closure step produces. So the shadow
      Hamiltonian’s *dimension* is fixed by the **closure** (and which labels
      show up in ``H`` and ``operator_set``), not by “same as ``H``’s size.”

    We still use the full ``(2^n)``-dimensional ``H`` in step 5 only to form
    commutators ``H @ P - P @ H`` with full Pauli matrices—implementation detail.
    """

    def __init__(
        self,
        operator_set: OperatorSet,
        H: Hamiltonian | Sequence[Hamiltonian],
        *,
        num_qubits: int | None = None,
        tol: float = 1e-10,
    ):
        """
        ``H`` may be a single ``Hamiltonian`` or a non-empty sequence of terms;
        terms are summed on the full ``num_qubits``-qubit space (see
        ``combined_hamiltonian_matrix``). ``self.H`` is always that summed
        ``Hamiltonian``. Full-domain terms are assumed to share one
        ``2**n x 2**n`` size; ``num_qubits`` is then ``n`` unless you pass
        ``num_qubits`` explicitly (required if every term is a
        ``LocalHamiltonian``). After closure, ``self.H_S`` is the reduced matrix.
        """
        self.operator_set = operator_set
        self.tol = float(tol)

        if isinstance(H, Hamiltonian):
            terms: list[Hamiltonian] = [H]
        else:
            terms = list(H)
            if not terms:
                raise ValueError("hamiltonians must be a non-empty sequence")

        nq = num_qubits if num_qubits is not None else _infer_num_qubits(terms)
        matrix_total = combined_hamiltonian_matrix(terms, nq)
        # Input model: always (2^n, 2^n). Output "shadow" matrix is H_S, (m, m), m = |closure|.
        self.H = Hamiltonian(matrix_total)

        matrix = np.asarray(self.H.matrix, dtype=np.complex128)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("H.matrix must be a square matrix")

        dim = matrix.shape[0]
        num_qubits = int(np.log2(dim))
        if 2**num_qubits != dim:
            raise ValueError(
                "H dimension must be a power of 2 to use a Pauli-string basis"
            )
        self.num_qubits = num_qubits

        # Step 1: convert H into a Pauli-string representation.
        pauli_terms: dict[str, complex] = {}
        normalization = 2**num_qubits
        for label_tuple in product("IXYZ", repeat=num_qubits):
            label = "".join(label_tuple)
            P = PauliString.from_string(label).matrix()
            coeff = np.trace(P.conj().T @ matrix) / normalization
            if abs(coeff) > self.tol:
                pauli_terms[label] = coeff
        self.pauli_decomposition = pauli_terms

        # Step 2: build the set of Pauli strings that appear in H.
        self.pauli_set = set(self.pauli_decomposition.keys())

        # Step 3: build one Pauli set covering all operators in operator_set.
        operator_pauli_set: set[str] = set()
        for operator in self.operator_set.operators:
            op_matrix = np.asarray(operator.matrix, dtype=np.complex128)
            if op_matrix.shape != matrix.shape:
                raise ValueError(
                    "all operators in operator_set must have the same matrix shape as H"
                )

            for label_tuple in product("IXYZ", repeat=num_qubits):
                label = "".join(label_tuple)
                P = PauliString.from_string(label).matrix()
                coeff = np.trace(P.conj().T @ op_matrix) / normalization
                if abs(coeff) > self.tol:
                    operator_pauli_set.add(label)
        self.operator_pauli_set = operator_pauli_set
        print(
            "Pauli counts -> "
            f"Hamiltonian set: {len(self.pauli_set)}, "
            f"Operator set union: {len(self.operator_pauli_set)}"
        )

        # Step 4: close operator Pauli strings under [·, h] for every Hamiltonian Pauli h.
        closure: set[str] = set(self.operator_pauli_set)
        q: deque[str] = deque(self.operator_pauli_set)
        while q:
            popped = q.popleft()
            popped_ps = PauliString.from_string(popped)
            for h_label in self.pauli_set:
                h_ps = PauliString.from_string(h_label)
                _coeff, com = popped_ps.commutator(h_ps)
                if com is None:
                    continue
                r_label = str(com)
                if r_label in closure:
                    continue
                closure.add(r_label)
                q.append(r_label)
        self.operator_pauli_closure = closure
        print(f"Operator closure size: {len(self.operator_pauli_closure)}")

        # Step 5: build H_S on the closure basis via commutator projection.
        self.basis = sorted(self.operator_pauli_closure)
        n = len(self.basis)
        H_S = np.zeros((n, n), dtype=np.complex128)
        basis_mats = [PauliString.from_string(label).matrix() for label in self.basis]

        for m, O_m in enumerate(basis_mats):
            C = matrix @ O_m - O_m @ matrix
            for mp, O_mp in enumerate(basis_mats):
                norm_sq = np.trace(O_mp.conj().T @ O_mp)
                H_S[m, mp] = -np.trace(O_mp @ C) / norm_sq
        self.H_S = H_S

    @property
    def shadow(self) -> np.ndarray:
        """The shadow Hamiltonian: ``(m, m)`` with ``m = |closure|``; not ``(2^n, 2^n)`` in general."""
        return self.H_S

    def get_H_S(self) -> np.ndarray:
        """
        Same as :attr:`shadow` — the shadow Hamiltonian in the closed Pauli
        basis, shape ``(m, m)`` with ``m = len(self.basis)``, independent of
        ``2^n`` (unless m happens to match by coincidence).
        """
        return self.H_S

    def is_unitary(self):
        return unitary(self.H_S)

    def is_hermitian(self):
        return hermitian(self.H_S)

    def __str__(self):
        return (
            "ShadowHamiltonian("
            f"full_H.shape={self.H.matrix.shape}, "
            f"shadow.shape={self.H_S.shape}, "
            f"n_qubits={self.num_qubits}"
            ")"
        )

    def __repr__(self):
        return (
            "ShadowHamiltonian("
            f"H.shape={self.H.matrix.shape}, "
            f"H_S.shape={self.H_S.shape}, "
            f"basis_size={len(self.basis)}, "
            f"tol={self.tol!r})"
        )
