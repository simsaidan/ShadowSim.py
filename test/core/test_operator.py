import numpy as np
import pytest

from shadowsim.core import LocalOperator, Operator, OperatorSet, PauliString, PauliSum
from shadowsim.core.operator import _coerce_pauli_sum


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


def test_operator_flags_are_non_callable_attributes():
    op = Operator(np.eye(2, dtype=np.complex128))
    flags = (
        op.is_hermitian,
        op.is_unitary,
        op.is_positive_semidefinite,
        op.is_negative_semidefinite,
        op.is_indefinite,
    )
    for flag in flags:
        assert isinstance(flag, (bool, np.bool_))
        assert not callable(flag)


def test_operator_equality_and_inequality():
    a = Operator(np.eye(2))
    b = Operator(np.eye(2))
    c = Operator(np.array([[0.0, 1.0], [1.0, 0.0]]))
    assert a == b
    assert a != c


def test_operator_str_and_repr():
    op = Operator(np.eye(2, dtype=np.complex128))
    assert "Operator(matrix=" in str(op)
    assert "Operator(matrix=" in repr(op)


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


def test_operator_from_pauli_label_is_lazy_and_names_itself():
    op = Operator("XII")
    assert op.name == "XII"
    assert op.pauli_sum is not None
    assert op._matrix_cache is None
    assert op.dimension == 8
    assert op.is_hermitian is True
    assert op._matrix_cache is None  # Hermiticity does not densify

    expected = PauliString.from_string("XII").matrix()
    assert np.allclose(op.matrix, expected)
    assert op._matrix_cache is not None


def test_operator_from_pauli_sum_expression_and_override_name():
    op = Operator("XXI + XYZ", name="obs")
    assert op.name == "obs"
    hand = PauliString.from_string("XXI").matrix() + PauliString.from_string("XYZ").matrix()
    assert np.allclose(op.matrix, hand)


def test_operator_from_pauli_string():
    op = Operator(PauliString.from_string("YZ"))
    assert op.name == "YZ"
    assert np.allclose(op.matrix, PauliString.from_string("YZ").matrix())


def test_operator_from_pauli_sum_object_and_lazy_str_repr():
    op = Operator(PauliSum.from_string("X"))
    assert "Operator(pauli_sum=" in str(op)
    assert "Operator(pauli_sum=" in repr(op)
    assert op._matrix_cache is None
    assert op.is_unitary is True  # densifies via non-Hermitian flag path
    assert op._matrix_cache is not None
    assert "Operator(matrix=" in str(op)


def test_operator_rejects_unsupported_input_types():
    with pytest.raises(TypeError, match="numpy array, str, PauliString, or PauliSum"):
        Operator(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="unsupported operator input type"):
        _coerce_pauli_sum(1.0)  # type: ignore[arg-type]


def test_operator_ensure_matrix_and_hermitian_fallbacks():
    broken = Operator.__new__(Operator)
    broken._pauli_sum = None
    broken._matrix_cache = None
    broken._flags_ready = False
    with pytest.raises(RuntimeError, match="neither a matrix cache nor a PauliSum"):
        broken.matrix

    partial = Operator.__new__(Operator)
    partial._pauli_sum = None
    partial._matrix_cache = np.eye(2, dtype=np.complex128)
    partial._flags_ready = False
    partial._is_hermitian = False
    partial._is_unitary = False
    partial._is_positive_semidefinite = False
    partial._is_negative_semidefinite = False
    partial._is_indefinite = False
    assert partial.is_hermitian is True
    assert partial._flags_ready is True
