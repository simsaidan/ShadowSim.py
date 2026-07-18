import numpy as np
import pytest

from src.core.local_operator import LocalOperator
from src.core.operator import Operator
from src.core.operator_set import OperatorSet


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
