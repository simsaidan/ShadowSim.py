"""Tests for shadow invariance diagnostics."""

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, OperatorSet
from shadowsim.shadow import InvarianceReport, check_invariance

X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def test_one_qubit_not_closed_reports_growth():
    """H = X, S = {Z}: closure adds Y."""
    report = check_invariance(OperatorSet([Operator(Z)]), Hamiltonian(X))

    assert isinstance(report, InvarianceReport)
    assert report.is_closed is False
    assert report.original_size == 1
    assert report.closure_size == 2
    assert report.growth == 1
    assert report.original_paulis == frozenset({"Z"})
    assert report.closure_paulis == frozenset({"Y", "Z"})
    assert report.added_paulis == frozenset({"Y"})
    assert report.h_s_is_hermitian is True
    assert report.num_qubits == 1
    assert report.used_sparse_pauli_path is False


def test_three_qubit_already_closed():
    """XII+IIX with {XII, YII, ZII, IIX} is already closed."""
    report = check_invariance(
        OperatorSet(["XII", "YII", "ZII", "IIX"]),
        [Hamiltonian("XII"), Hamiltonian("IIX")],
    )

    expected = frozenset({"XII", "YII", "ZII", "IIX"})
    assert report.is_closed is True
    assert report.growth == 0
    assert report.original_size == 4
    assert report.closure_size == 4
    assert report.original_paulis == expected
    assert report.closure_paulis == expected
    assert report.added_paulis == frozenset()
    assert report.h_s_is_hermitian is True
    assert report.num_qubits == 3
    assert report.used_sparse_pauli_path is True


def test_sparse_and_dense_paths_agree():
    dense = check_invariance(OperatorSet([Operator(Z)]), Hamiltonian(X))
    sparse = check_invariance(OperatorSet(["Z"]), Hamiltonian("X"))

    assert dense.used_sparse_pauli_path is False
    assert sparse.used_sparse_pauli_path is True
    assert sparse.is_closed == dense.is_closed
    assert sparse.growth == dense.growth
    assert sparse.original_paulis == dense.original_paulis
    assert sparse.closure_paulis == dense.closure_paulis
    assert sparse.added_paulis == dense.added_paulis
    assert sparse.h_s_is_hermitian == dense.h_s_is_hermitian
    assert sparse.num_qubits == dense.num_qubits


def test_local_hamiltonian_requires_explicit_num_qubits():
    with pytest.raises(ValueError, match="pass num_qubits="):
        check_invariance(
            OperatorSet([Operator(Z)]),
            [LocalHamiltonian(X, [0])],
        )

    report = check_invariance(
        OperatorSet([Operator(Z)]),
        [LocalHamiltonian(X, [0])],
        num_qubits=1,
    )
    assert report.used_sparse_pauli_path is False
    assert report.growth == 1
    assert report.added_paulis == frozenset({"Y"})
    assert report.h_s_is_hermitian is True


def test_check_invariance_rejects_empty_hamiltonian_sequence():
    with pytest.raises(ValueError, match="non-empty sequence"):
        check_invariance(OperatorSet([Operator(Z)]), [])
