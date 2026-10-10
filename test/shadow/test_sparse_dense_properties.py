"""Property catalog: sparse vs dense shadow agreement.

Invariants exercised by Hypothesis tests in this module:

* ``assert_core_agreement`` holds for random Pauli Hamiltonians / observables.
* ``assert_shadow_agreement`` holds for the same models (n ≤ 4; dense path capped).
* Path flags differ (``used_sparse_pauli_path``) while numerical outputs match.
"""

from hypothesis import given
from strategies.pauli_random import MAX_PROPERTY_QUBITS, sparse_pauli_models
from strategies.shadow_agreement import assert_core_agreement, assert_shadow_agreement

from shadowsim.core import Hamiltonian, OperatorSet


@given(sparse_pauli_models(max_n=MAX_PROPERTY_QUBITS, max_terms=3, max_obs=2))
def test_sparse_dense_core_and_shadow_agree(model: tuple[Hamiltonian, OperatorSet, int]):
    hamiltonian, operator_set, _n = model
    assert_core_agreement(hamiltonian, operator_set)
    sparse, dense = assert_shadow_agreement(hamiltonian, operator_set)
    assert sparse.used_sparse_pauli_path is True
    assert dense.used_sparse_pauli_path is False
