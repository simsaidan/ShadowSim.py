"""Sparse↔dense agreement helpers shared by regression and property tests."""

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, OperatorSet
from shadowsim.shadow import ShadowHamiltonian
from strategies.pauli_random import ATOL, RTOL


def densify_hamiltonians(
    hamiltonians: Hamiltonian | list[Hamiltonian],
) -> Hamiltonian | list[Hamiltonian]:
    """Force the dense path by wrapping materialized matrices."""
    if isinstance(hamiltonians, Hamiltonian):
        return Hamiltonian(hamiltonians.matrix)
    return [Hamiltonian(h.matrix) for h in hamiltonians]


def densify_operator_set(operator_set: OperatorSet) -> OperatorSet:
    """Force dense observables (``pauli_sum is None``)."""
    return OperatorSet([Operator(op.matrix) for op in operator_set.operators])


def _as_hamiltonian_list(hamiltonians: Hamiltonian | list[Hamiltonian]) -> list[Hamiltonian]:
    if isinstance(hamiltonians, Hamiltonian):
        return [hamiltonians]
    return list(hamiltonians)


def assert_core_agreement(
    hamiltonians: Hamiltonian | list[Hamiltonian],
    operator_set: OperatorSet,
) -> None:
    """Sparse label objects densify to the same matrices as ndarray constructors."""
    for h in _as_hamiltonian_list(hamiltonians):
        assert h.pauli_sum is not None
        dense_h = Hamiltonian(h.matrix)
        assert dense_h.pauli_sum is None
        assert np.allclose(h.matrix, dense_h.matrix, atol=ATOL, rtol=RTOL)

    terms = _as_hamiltonian_list(hamiltonians)
    if len(terms) > 1:
        merged = terms[0].pauli_sum
        assert merged is not None
        for h in terms[1:]:
            assert h.pauli_sum is not None
            merged = merged + h.pauli_sum
        combined = sum((h.matrix for h in terms), start=np.zeros_like(terms[0].matrix))
        assert np.allclose(Hamiltonian(merged).matrix, combined, atol=ATOL, rtol=RTOL)

    for op in operator_set.operators:
        assert op.pauli_sum is not None
        dense_op = Operator(op.matrix)
        assert dense_op.pauli_sum is None
        assert np.allclose(op.matrix, dense_op.matrix, atol=ATOL, rtol=RTOL)


def assert_shadow_agreement(
    hamiltonians: Hamiltonian | list[Hamiltonian],
    operator_set: OperatorSet,
    *,
    tol: float = 1e-10,
) -> tuple[ShadowHamiltonian, ShadowHamiltonian]:
    """Build sparse and dense shadows; assert path flags and numerical equality."""
    dense_h = densify_hamiltonians(hamiltonians)
    dense_ops = densify_operator_set(operator_set)

    sparse = ShadowHamiltonian(operator_set, hamiltonians, tol=tol)
    dense = ShadowHamiltonian(dense_ops, dense_h, tol=tol)

    assert sparse.used_sparse_pauli_path is True
    assert dense.used_sparse_pauli_path is False
    assert sparse.basis == dense.basis
    assert sparse.operator_pauli_closure == dense.operator_pauli_closure
    assert set(sparse.pauli_decomposition) == set(dense.pauli_decomposition)
    for lab in sparse.pauli_decomposition:
        assert sparse.pauli_decomposition[lab] == pytest.approx(
            dense.pauli_decomposition[lab],
            rel=RTOL,
            abs=ATOL,
        )
    assert np.allclose(sparse.H_S, dense.H_S, atol=ATOL, rtol=RTOL)
    assert sparse.is_hermitian() == dense.is_hermitian()
    return sparse, dense
