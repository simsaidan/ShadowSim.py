"""Property catalog: ``check_invariance`` / IP closure.

Invariants exercised by Hypothesis tests in this module:

* Sparse and dense paths agree on closure reports (n ≤ 3).
* Closure is monotonic: ``original ⊆ closure``, ``growth = |closure| - |original|``.
* Closure is idempotent: closing an already-closed set adds nothing.
"""

from hypothesis import given
from strategies.pauli_random import MAX_SHADOW_PROPERTY_QUBITS, sparse_pauli_models
from strategies.shadow_agreement import densify_hamiltonians, densify_operator_set

from shadowsim.core import Hamiltonian, OperatorSet
from shadowsim.shadow import check_invariance


@given(sparse_pauli_models(max_n=MAX_SHADOW_PROPERTY_QUBITS, max_terms=3, max_obs=2))
def test_invariance_sparse_and_dense_paths_agree(model: tuple[Hamiltonian, OperatorSet, int]):
    hamiltonian, operator_set, _n = model
    sparse = check_invariance(operator_set, hamiltonian)
    dense = check_invariance(
        densify_operator_set(operator_set),
        densify_hamiltonians(hamiltonian),
    )

    assert sparse.used_sparse_pauli_path is True
    assert dense.used_sparse_pauli_path is False
    assert sparse.is_closed == dense.is_closed
    assert sparse.growth == dense.growth
    assert sparse.original_size == dense.original_size
    assert sparse.closure_size == dense.closure_size
    assert sparse.original_paulis == dense.original_paulis
    assert sparse.closure_paulis == dense.closure_paulis
    assert sparse.added_paulis == dense.added_paulis
    assert sparse.h_s_is_hermitian == dense.h_s_is_hermitian
    assert sparse.num_qubits == dense.num_qubits


@given(sparse_pauli_models(max_n=MAX_SHADOW_PROPERTY_QUBITS, max_terms=3, max_obs=2))
def test_invariance_closure_is_monotonic(model: tuple[Hamiltonian, OperatorSet, int]):
    hamiltonian, operator_set, _n = model
    report = check_invariance(operator_set, hamiltonian)

    assert report.original_paulis <= report.closure_paulis
    assert report.added_paulis == report.closure_paulis - report.original_paulis
    assert report.growth == report.closure_size - report.original_size
    assert report.growth == len(report.added_paulis)
    assert report.is_closed == (report.growth == 0)


@given(sparse_pauli_models(max_n=MAX_SHADOW_PROPERTY_QUBITS, max_terms=3, max_obs=2))
def test_invariance_closure_is_idempotent(model: tuple[Hamiltonian, OperatorSet, int]):
    hamiltonian, operator_set, _n = model
    first = check_invariance(operator_set, hamiltonian)
    closed_ops = OperatorSet(sorted(first.closure_paulis))
    second = check_invariance(closed_ops, hamiltonian)

    assert second.is_closed is True
    assert second.growth == 0
    assert second.added_paulis == frozenset()
    assert second.closure_paulis == first.closure_paulis
    assert second.original_paulis == first.closure_paulis
