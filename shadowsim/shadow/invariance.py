"""Invariance checks for shadow constructions.

The invariance property (IP) from Somma et al. (arXiv:2407.21775) requires that
``[H, O_m]`` stays in the span of the operator set ``S`` for every ``O_m`` in
``S``.  When IP holds, expectations of operators in ``S`` evolve among
themselves under ``H``.

This module diagnoses whether a user-supplied ``S`` is already closed under
``ad_H`` (in the Pauli label basis) and reports how much growth is needed to
close it.  It does not change ``ShadowHamiltonian`` construction, which still
auto-closes.

TODO: Suggest a change-of-basis ``A`` so that the transformed shadow matrix
``A H_S`` (or equivalent on ``A O``) is Hermitian when IP holds but ``H_S`` is
not (paper Sec. 2 / bosonic example).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.operator_set import OperatorSet
from shadowsim.shadow.shadow_hamiltonian import (
    _assemble_h_s,
    _close_operator_paulis,
    _pauli_model_from_inputs,
)
from shadowsim.utils.hermitian import hermitian


@dataclass(frozen=True)
class InvarianceReport:
    """Diagnostic for whether ``H`` and an operator set satisfy the IP.

    Attributes:
        is_closed: Whether the original Pauli support of ``S`` already equals
            its closure under commutators with ``H``.
        original_size: Number of Pauli labels in the original operator set.
        closure_size: Number of Pauli labels after ad_H closure.
        growth: ``closure_size - original_size``.
        original_paulis: Pauli labels appearing in the original operator set.
        closure_paulis: Pauli labels after closure.
        added_paulis: Labels in the closure that were not in the original set.
        h_s_is_hermitian: Whether ``H_S`` on the closed basis is Hermitian
            (needed for unitary shadow Schrödinger evolution).
        num_qubits: Qubit count used for the Pauli presentation.
        used_sparse_pauli_path: Whether the sparse Pauli path was used.
    """

    is_closed: bool
    original_size: int
    closure_size: int
    growth: int
    original_paulis: frozenset[str]
    closure_paulis: frozenset[str]
    added_paulis: frozenset[str]
    h_s_is_hermitian: bool
    num_qubits: int
    used_sparse_pauli_path: bool


def check_invariance(
    operator_set: OperatorSet,
    H: Hamiltonian | Sequence[Hamiltonian],
    *,
    num_qubits: int | None = None,
    tol: float = 1e-10,
) -> InvarianceReport:
    """Check whether ``H`` and ``operator_set`` satisfy the invariance property.

    Uses the same sparse/dense Pauli presentation as ``ShadowHamiltonian``.
    Reports whether the original Pauli support of ``S`` is already closed under
    commutators with ``H``, and how many labels must be added to close it.
    Also reports whether the closed-basis ``H_S`` is Hermitian.

    Args:
        operator_set: Observables whose Pauli support defines ``S``.
        H: A single ``Hamiltonian`` or a non-empty sequence of terms.
        num_qubits: Qubit count; inferred when possible (required if every term
            is a ``LocalHamiltonian``).
        tol: Magnitude threshold for keeping Pauli coefficients.

    Returns:
        An ``InvarianceReport`` summarizing closure and Hermiticity.
    """
    model = _pauli_model_from_inputs(
        operator_set,
        H,
        num_qubits=num_qubits,
        tol=tol,
    )
    original = set(model.operator_pauli_set)
    closure = _close_operator_paulis(original, set(model.pauli_set))
    added = closure - original
    basis = sorted(closure)
    h_s = _assemble_h_s(basis, model.pauli_decomposition)

    return InvarianceReport(
        is_closed=not added,
        original_size=len(original),
        closure_size=len(closure),
        growth=len(added),
        original_paulis=frozenset(original),
        closure_paulis=frozenset(closure),
        added_paulis=frozenset(added),
        h_s_is_hermitian=hermitian(h_s),
        num_qubits=model.num_qubits,
        used_sparse_pauli_path=model.used_sparse_pauli_path,
    )
