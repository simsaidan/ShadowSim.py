"""Tests for shadowsim.core.operator_set."""

import numpy as np
import pytest

from shadowsim.core import Operator, OperatorSet


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


def test_operator_set_coerces_pauli_labels():
    op_set = OperatorSet(["XII", "YII", "XXI + XYZ"])
    assert len(op_set) == 3
    assert op_set[0].name == "XII"
    assert op_set[2].pauli_sum is not None
    assert "XYZ" in op_set[2].pauli_sum.terms
