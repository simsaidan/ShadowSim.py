"""Property catalog: ``Hamiltonian`` / ``LocalHamiltonian``.

Invariants exercised by Hypothesis tests in this module:

* Non-Hermitian inputs are rejected; real-coefficient PauliSums are accepted.
* Accepted Hamiltonians have Hermitian matrices.
* Local embedding equals identity-padded tensor product and preserves Hermiticity.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL, hermitian_matrices, real_pauli_sums

from shadowsim.core import Hamiltonian, LocalHamiltonian, PauliSum
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.tensor import tensor


@given(real_pauli_sums())
def test_hamiltonian_accepts_real_pauli_sums(ps: PauliSum):
    h = Hamiltonian(ps)
    assert h.pauli_sum is not None
    assert h.is_hermitian is True
    assert hermitian(h.matrix)


@given(real_pauli_sums())
def test_hamiltonian_rejects_complex_pauli_sums(ps: PauliSum):
    terms = {lab: complex(coeff) + 0.5j for lab, coeff in ps.terms.items()}
    with pytest.raises(AssertionError, match="Hermitian"):
        Hamiltonian(PauliSum(terms))


@given(hermitian_matrices(min_dim=2, max_dim=8))
def test_hamiltonian_accepts_hermitian_dense_matrices(matrix: np.ndarray):
    h = Hamiltonian(matrix)
    assert h.pauli_sum is None
    assert hermitian(h.matrix)


@given(st.integers(min_value=2, max_value=8))
def test_hamiltonian_rejects_non_hermitian_dense_matrices(dim: int):
    matrix = np.eye(dim, dtype=np.complex128)
    matrix[0, 1] = 1.0 + 2j
    with pytest.raises(AssertionError, match="Hermitian"):
        Hamiltonian(matrix)


@given(
    st.sampled_from(["X", "Y", "Z"]),
    st.integers(min_value=0, max_value=2),
    st.integers(min_value=1, max_value=3),
)
def test_local_hamiltonian_embedding_matches_identity_padding(label: str, start: int, pad_right: int):
    from shadowsim.core import Pauli

    local_matrix = Pauli(label).matrix()
    sites = [start]
    total_sites = start + 1 + pad_right
    local = LocalHamiltonian(local_matrix, sites=sites, local_dim=2)
    full = local.to_full_hamiltonian(total_sites)

    eye = np.eye(2, dtype=np.complex128)
    expected = tensor([eye] * start + [local_matrix] + [eye] * pad_right)
    assert np.allclose(full.matrix, expected, atol=ATOL, rtol=RTOL)
    assert hermitian(full.matrix)


@given(real_pauli_sums(min_n=1, max_n=MAX_PROPERTY_QUBITS))
def test_hamiltonian_to_local_round_trip_preserves_matrix(ps: PauliSum):
    h = Hamiltonian(ps)
    local = h.to_local_hamiltonian(local_dim=2)
    full = local.to_full_hamiltonian(total_sites=ps.num_qubits)
    assert np.allclose(full.matrix, h.matrix, atol=ATOL, rtol=RTOL)
