"""Shadow Hamiltonian construction and closure."""

from collections import deque
from collections.abc import Sequence
from itertools import product

import numpy as np

from shadowsim.core.combined_hamiltonian_matrix import combined_hamiltonian_matrix
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator_set import OperatorSet
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.unitary import unitary


def _full_domain_dimension(h: Hamiltonian) -> int:
    """Return Hilbert-space dimension without densifying Pauli-backed terms."""
    return int(h.dimension)


def _infer_num_qubits(terms: list[Hamiltonian]) -> int:
    """Infer ``num_qubits`` from full-domain terms.

    All such terms must share the same Hilbert-space dimension ``2**n``.
    Pauli-backed terms use ``dimension`` and do not materialize matrices.
    """
    d_ref: int | None = None
    for h in terms:
        if isinstance(h, LocalHamiltonian):
            continue
        d = _full_domain_dimension(h)
        if d <= 0 or (d & (d - 1)) != 0:
            raise ValueError(f"full-domain Hamiltonian matrix dimension must be a power of 2, got {d}")
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


def _can_use_sparse_pauli_path(terms: list[Hamiltonian], operator_set: OperatorSet) -> bool:
    """Return whether H and observables already carry Pauli decompositions."""
    for h in terms:
        if isinstance(h, LocalHamiltonian) or h.pauli_sum is None:
            return False
    return all(op.pauli_sum is not None for op in operator_set.operators)


def _merge_pauli_hamiltonians(terms: list[Hamiltonian]) -> PauliSum:
    """Sum Pauli-backed Hamiltonian terms without densifying."""
    merged = terms[0].pauli_sum
    if merged is None:
        raise ValueError("expected Pauli-backed Hamiltonian terms")
    for h in terms[1:]:
        ps = h.pauli_sum
        if ps is None:
            raise ValueError("expected Pauli-backed Hamiltonian terms")
        merged = merged + ps
    return merged


def _pauli_terms_above_tol(pauli_sum: PauliSum, tol: float) -> dict[str, complex]:
    """Copy PauliSum terms with magnitude above ``tol``."""
    return {lab: complex(c) for lab, c in pauli_sum.terms.items() if abs(c) > tol}


def _operator_pauli_labels(operator_set: OperatorSet, tol: float) -> set[str]:
    """Union of Pauli labels appearing in Pauli-backed observables."""
    labels: set[str] = set()
    for operator in operator_set.operators:
        ps = operator.pauli_sum
        if ps is None:
            raise ValueError("expected Pauli-backed operators")
        for lab, coeff in ps.terms.items():
            if abs(coeff) > tol:
                labels.add(lab)
    return labels


def _dense_pauli_decomposition(matrix: np.ndarray, num_qubits: int, tol: float) -> dict[str, complex]:
    """Hilbert–Schmidt expand a dense matrix onto the Pauli basis (``4^n`` scan)."""
    pauli_terms: dict[str, complex] = {}
    normalization = 2**num_qubits
    for label_tuple in product("IXYZ", repeat=num_qubits):
        label = "".join(label_tuple)
        P = PauliString.from_string(label).matrix()
        coeff = np.trace(P.conj().T @ matrix) / normalization
        if abs(coeff) > tol:
            pauli_terms[label] = complex(coeff)
    return pauli_terms


def _assemble_h_s(basis: list[str], pauli_decomposition: dict[str, complex]) -> np.ndarray:
    """Build ``H_S`` from commutator structure constants in the closed Pauli basis.

    For ``H = Σ_h c_h h`` and basis element ``O_m``, if ``[h, O_m] = α R`` then
    ``H_S[m, idx(R)] += -c_h α``. Hilbert–Schmidt norms cancel for Pauli strings.
    """
    n = len(basis)
    index = {lab: i for i, lab in enumerate(basis)}
    H_S = np.zeros((n, n), dtype=np.complex128)
    h_terms = [(c_h, PauliString.from_string(h_lab)) for h_lab, c_h in pauli_decomposition.items()]
    for m, lab_m in enumerate(basis):
        O_m = PauliString.from_string(lab_m)
        for c_h, h_ps in h_terms:
            alpha, com = h_ps.commutator(O_m)
            if com is None:
                continue
            mp = index.get(str(com))
            if mp is not None:
                H_S[m, mp] += -c_h * alpha
    return H_S


def _close_operator_paulis(operator_pauli_set: set[str], pauli_set: set[str]) -> set[str]:
    """BFS-close operator Pauli labels under commutators with Hamiltonian Paulis."""
    closure: set[str] = set(operator_pauli_set)
    q: deque[str] = deque(operator_pauli_set)
    while q:
        popped = q.popleft()
        popped_ps = PauliString.from_string(popped)
        for h_label in pauli_set:
            h_ps = PauliString.from_string(h_label)
            _coeff, com = popped_ps.commutator(h_ps)
            if com is None:
                continue
            r_label = str(com)
            if r_label in closure:
                continue
            closure.add(r_label)
            q.append(r_label)
    return closure


class ShadowHamiltonian:
    """Store the input model ``H`` and the reduced shadow matrix ``H_S``.

    There are two objects:

    - ``self.H``: the **input** model on the full qubit space. On the sparse Pauli
      path this is a PauliSum-backed ``Hamiltonian`` (no ``2^n`` matrix until
      ``.matrix`` is accessed). On the dense fallback it is the summed
      ``(2^n, 2^n)`` matrix.
    - ``self.H_S`` (also ``.shadow`` / ``get_H_S()``): the **actual shadow
      object**—commutator matrix in the **closed Pauli label basis** only, shape
      **``(m, m)``** with **``m = |closure|``**. That size does **not** have to
      equal ``2^n``; it is whatever the closure step produces.

    When ``H`` and every observable already expose a ``pauli_sum``, construction
    stays in label/coeff space (no ``4^n`` tomography, no full-space matrix
    multiplies). Otherwise the dense path densifies once, expands via traces,
    then shares the same structure-constant assembly for ``H_S``.
    """

    def __init__(
        self,
        operator_set: OperatorSet,
        H: Hamiltonian | Sequence[Hamiltonian],
        *,
        num_qubits: int | None = None,
        tol: float = 1e-10,
        verbose: bool = False,
    ):
        """Build a shadow Hamiltonian from an operator set and Hamiltonian terms.

        ``H`` may be a single ``Hamiltonian`` or a non-empty sequence of terms.
        If every term and every observable is Pauli-backed, terms are merged as
        PauliSums without densifying. Otherwise terms are summed on the full
        ``num_qubits``-qubit space via ``combined_hamiltonian_matrix``.
        ``num_qubits`` is inferred when possible (required if every term is a
        ``LocalHamiltonian``). After closure, ``self.H_S`` is the reduced matrix.
        Set ``verbose=True`` to print Pauli-set and closure progress.
        """
        self.operator_set = operator_set
        self.tol = float(tol)
        self.verbose = verbose

        if isinstance(H, Hamiltonian):
            terms: list[Hamiltonian] = [H]
        else:
            terms = list(H)
            if not terms:
                raise ValueError("hamiltonians must be a non-empty sequence")

        nq = num_qubits if num_qubits is not None else _infer_num_qubits(terms)
        use_sparse = _can_use_sparse_pauli_path(terms, operator_set)
        self.used_sparse_pauli_path = use_sparse

        if use_sparse:
            merged = _merge_pauli_hamiltonians(terms)
            if merged.num_qubits != nq:
                raise ValueError(
                    f"num_qubits={nq} does not match Pauli word length {merged.num_qubits}"
                )
            for operator in self.operator_set.operators:
                ps = operator.pauli_sum
                if ps is None or ps.num_qubits != nq:
                    raise ValueError("all operators in operator_set must have the same matrix shape as H")
            self.H = Hamiltonian(merged)
            self.num_qubits = nq
            self.pauli_decomposition = _pauli_terms_above_tol(merged, self.tol)
            self.pauli_set = set(self.pauli_decomposition.keys())
            self.operator_pauli_set = _operator_pauli_labels(self.operator_set, self.tol)
        else:
            matrix_total = combined_hamiltonian_matrix(terms, nq)
            if matrix_total.ndim != 2 or matrix_total.shape[0] != matrix_total.shape[1]:
                raise ValueError("H.matrix must be a square matrix")

            dim = matrix_total.shape[0]
            inferred_nq = int(np.log2(dim)) if dim > 0 else -1
            if inferred_nq < 0 or 2**inferred_nq != dim:
                raise ValueError("H dimension must be a power of 2 to use a Pauli-string basis")
            self.num_qubits = inferred_nq
            self.H = Hamiltonian(matrix_total)

            matrix = np.asarray(self.H.matrix, dtype=np.complex128)
            self.pauli_decomposition = _dense_pauli_decomposition(matrix, self.num_qubits, self.tol)
            self.pauli_set = set(self.pauli_decomposition.keys())

            operator_pauli_set: set[str] = set()
            for operator in self.operator_set.operators:
                op_matrix = np.asarray(operator.matrix, dtype=np.complex128)
                if op_matrix.shape != matrix.shape:
                    raise ValueError("all operators in operator_set must have the same matrix shape as H")
                operator_pauli_set.update(
                    _dense_pauli_decomposition(op_matrix, self.num_qubits, self.tol).keys()
                )
            self.operator_pauli_set = operator_pauli_set

        if self.verbose:
            print(
                "Pauli counts -> "
                f"Hamiltonian set: {len(self.pauli_set)}, "
                f"Operator set union: {len(self.operator_pauli_set)}"
            )

        self.operator_pauli_closure = _close_operator_paulis(self.operator_pauli_set, self.pauli_set)
        if self.verbose:
            print(f"Operator closure size: {len(self.operator_pauli_closure)}")

        self.basis = sorted(self.operator_pauli_closure)
        self.H_S = _assemble_h_s(self.basis, self.pauli_decomposition)

    @property
    def shadow(self) -> np.ndarray:
        """The shadow Hamiltonian: ``(m, m)`` with ``m = |closure|``; not ``(2^n, 2^n)`` in general."""
        return self.H_S

    def get_H_S(self) -> np.ndarray:
        """Return the shadow Hamiltonian in the closed Pauli basis.

        Same as :attr:`shadow`. Shape ``(m, m)`` with ``m = len(self.basis)``,
        independent of ``2^n`` (unless m happens to match by coincidence).
        """
        return self.H_S

    def is_unitary(self):
        """Return whether the shadow Hamiltonian matrix is unitary."""
        return unitary(self.H_S)

    def is_hermitian(self):
        """Return whether the shadow Hamiltonian matrix is Hermitian."""
        return hermitian(self.H_S)

    def __str__(self):
        """Return a string representation of the ShadowHamiltonian."""
        if self.used_sparse_pauli_path:
            h_part = f"pauli_terms={len(self.pauli_decomposition)}"
        else:
            h_part = f"full_H.shape={self.H.matrix.shape}"
        return (
            "ShadowHamiltonian("
            f"{h_part}, "
            f"shadow.shape={self.H_S.shape}, "
            f"n_qubits={self.num_qubits}"
            ")"
        )

    def __repr__(self):
        """Return a string representation of the ShadowHamiltonian."""
        if self.used_sparse_pauli_path:
            h_part = f"pauli_terms={len(self.pauli_decomposition)}"
        else:
            h_part = f"H.shape={self.H.matrix.shape}"
        return (
            "ShadowHamiltonian("
            f"{h_part}, "
            f"H_S.shape={self.H_S.shape}, "
            f"basis_size={len(self.basis)}, "
            f"sparse={self.used_sparse_pauli_path!r}, "
            f"tol={self.tol!r}, "
            f"verbose={self.verbose!r})"
        )
