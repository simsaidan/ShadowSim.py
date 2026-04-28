"""Tests for src.core.operator_set."""

import numpy as np
import pytest

from src.core.operator_set import LocalOperator, Operator, OperatorSet


def test_operator_init_sets_basic_fields_and_flags():
    mat = np.eye(2, dtype=np.complex128)
    op = Operator(mat, name="I")
    assert op.name == "I"
    assert op.dimension == 2
    assert op.is_hermitian is True
    assert op.is_unitary is True
    assert bool(op.is_positive_semidefinite)
    assert not bool(op.is_negative_semidefinite)
    assert not bool(op.is_indefinite)


def test_operator_sign_flags_for_indefinite_matrix():
    op = Operator(np.diag([1.0, -2.0]))
    assert not bool(op.is_positive_semidefinite)
    assert not bool(op.is_negative_semidefinite)
    assert bool(op.is_indefinite)


def test_operator_equality_and_inequality():
    a = Operator(np.eye(2))
    b = Operator(np.eye(2))
    c = Operator(np.array([[0.0, 1.0], [1.0, 0.0]]))
    assert a == b
    assert a != c


def test_operator_set_name_updates_name_field():
    op = Operator(np.eye(2))
    op.set_name("X")
    assert op.name == "X"
    op.set_name(None)
    assert op.name is None


def test_operator_set_name_validates_type():
    op = Operator(np.eye(2))
    with pytest.raises(AssertionError, match="name must be a string or None"):
        op.set_name(1)  # type: ignore[arg-type]


def test_operator_to_operator_set_wraps_single_operator():
    op = Operator(np.eye(2))
    op_set = op.to_operator_set()
    assert isinstance(op_set, OperatorSet)
    assert len(op_set) == 1
    assert op_set[0] == op


def test_operator_to_local_operator_builds_local_operator():
    op = Operator(np.eye(4))
    local = op.to_local_operator(sites=[0, 1], local_dim=2)
    assert isinstance(local, LocalOperator)
    assert local.sites == [0, 1]
    assert local.local_dim == 2
    assert local.matrix.shape == (4, 4)


def test_local_operator_requires_square_matrix():
    with pytest.raises(AssertionError, match="square 2D array"):
        LocalOperator(np.array([[1.0, 0.0, 0.0]]), sites=[0], local_dim=2)


def test_local_operator_requires_contiguous_unique_integer_sites():
    mat = np.eye(4)
    with pytest.raises(AssertionError, match="all sites must be unique"):
        LocalOperator(mat, sites=[0, 0], local_dim=2)
    with pytest.raises(AssertionError, match="all sites must be integers"):
        LocalOperator(mat, sites=[0, "1"], local_dim=2)
    with pytest.raises(AssertionError, match="contiguous range"):
        LocalOperator(mat, sites=[0, 2], local_dim=2)


def test_local_operator_rejects_dimension_mismatch():
    mat = np.eye(4)
    with pytest.raises(ValueError, match="invalid number of sites"):
        LocalOperator(mat, sites=[0], local_dim=2)


def test_local_operator_to_full_operator_adds_identity_padding():
    local = LocalOperator(np.eye(4), sites=[1, 2], local_dim=2)
    full = local.to_full_operator(total_sites=4)
    expected = np.kron(np.eye(2), np.kron(np.eye(4), np.eye(2)))
    assert isinstance(full, Operator)
    assert full.matrix.shape == (16, 16)
    assert np.allclose(full.matrix, expected)


def test_local_operator_to_full_operator_handles_high_index_block():
    local = LocalOperator(np.eye(8), sites=[3, 4, 5], local_dim=2)
    full = local.to_full_operator(total_sites=6)
    expected = np.kron(np.eye(8), np.eye(8))
    assert np.allclose(full.matrix, expected)


def test_local_operator_to_full_operator_validates_total_sites():
    local = LocalOperator(np.eye(4), sites=[1, 2], local_dim=2)
    with pytest.raises(AssertionError, match="total_sites must be an integer"):
        local.to_full_operator(4.0)  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match="total_sites must be positive"):
        local.to_full_operator(0)
    with pytest.raises(ValueError, match="too small"):
        local.to_full_operator(2)


def test_operator_set_init_and_basic_protocols():
    ops = [Operator(np.eye(2)), Operator(np.array([[0.0, 1.0], [1.0, 0.0]]))]
    op_set = OperatorSet(ops)
    assert len(op_set) == 2
    assert list(iter(op_set)) == ops
    assert op_set[0] == ops[0]
    assert "operator_count=2" in str(op_set)
    assert "OperatorSet(" in repr(op_set)


def test_operator_set_rejects_invalid_input_types():
    with pytest.raises(AssertionError, match="operators must be a list"):
        OperatorSet(tuple())  # type: ignore[arg-type]
    with pytest.raises(AssertionError, match="all operators must be Operator objects"):
        OperatorSet([np.eye(2)])  # type: ignore[list-item]


def test_operator_set_getitem_validates_index():
    op_set = OperatorSet([Operator(np.eye(2))])
    with pytest.raises(AssertionError, match="index must be an integer"):
        _ = op_set["0"]  # type: ignore[index]
    with pytest.raises(AssertionError, match="within the range"):
        _ = op_set[2]
