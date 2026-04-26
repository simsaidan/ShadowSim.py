from __future__ import annotations

from collections import deque
from itertools import product

import numpy as np

from src.core.hamiltonian import Hamiltonian
from src.core.operator_set import OperatorSet
from src.core.pauli import PauliString
from src.core.utils import unitary


class ShadowHamiltonian:
    def __init__(
        self,
        operator_set: OperatorSet,
        H: Hamiltonian,
        *,
        tol: float = 1e-10,
    ):
        self.operator_set = operator_set
        self.H = H
        self.tol = float(tol)

        matrix = np.asarray(H.matrix, dtype=np.complex128)
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

    def get_H_S(self):
        return self.H_S

    def is_unitary(self):
        return unitary(self.H_S)

    def is_hermitian(self):
        return np.allclose(self.H_S, self.H_S.conj().T)
