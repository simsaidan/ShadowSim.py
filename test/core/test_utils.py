"""Tests for src.core.utils helpers."""

import numpy as np
import pytest

from src.core.utils import (
    flip_dict,
    hermitian,
    indefinite,
    negative_definite,
    negative_semidefinite,
    next_power_of_two,
    positive_definite,
    positive_semidefinite,
    tensor,
    unitary,
)


# --- Pauli / small fixed matrices ---
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_HAD = np.array([[1.0, 1.0], [1.0, -1.0]], dtype=np.complex128) / np.sqrt(2)


@pytest.mark.parametrize(
    "d, expected",
    [
        ({}, {}),
        ({"01": 2}, {"10": 2}),
        ({"001": 1, "110": 2, "a": 3}, {"100": 1, "011": 2, "a": 3}),
        ({"aba": 7}, {"aba": 7}),
    ],
)
def test_flip_dict_reverses_keys(d, expected):
    assert flip_dict(d) == expected


def test_flip_dict_preserves_value_types():
    arr = np.array([1, 2])
    d = {"xy": 1, "zz": "hello", "ab": [1, 2, 3], "01": arr}
    out = flip_dict(d)
    assert out["yx"] == 1
    assert out["zz"] == "hello"
    assert out["ba"] == [1, 2, 3]
    assert out["10"] is arr


def test_flip_dict_does_not_mutate_input():
    d = {"01": 0, "ab": 1}
    d_copy = dict(d)
    _ = flip_dict(d)
    assert d == d_copy


def test_flip_dict_returns_new_dict():
    d = {"0": 1}
    out = flip_dict(d)
    assert out is not d
    out["0"] = 99
    assert d == {"0": 1}


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 4),
        (4, 4),
        (5, 8),
        (7, 8),
        (8, 8),
        (9, 16),
        (15, 16),
        (16, 16),
        (17, 32),
        (1023, 1024),
        (1024, 1024),
    ],
)
def test_next_power_of_two(n, expected):
    assert next_power_of_two(n) == expected


def test_next_power_of_two_rejects_negative():
    with pytest.raises(AssertionError):
        next_power_of_two(-1)


def test_next_power_of_two_rejects_non_int():
    with pytest.raises(AssertionError):
        next_power_of_two(3.0)


def test_unitary_identity_and_paulis():
    assert unitary(np.eye(2))
    assert unitary(np.eye(3))
    assert unitary(_X)
    assert unitary(_Y)
    assert unitary(_Z)


def test_unitary_hadamard_phase():
    assert unitary(_HAD)
    assert unitary(np.diag(np.exp([0.5j, -0.5j])))


def test_unitary_random_via_qr():
    rng = np.random.default_rng(0)
    q, _ = np.linalg.qr(rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4)))
    assert unitary(q)


def test_unitary_false_for_non_unitary():
    assert not unitary(np.array([[1.0, 2.0], [0.0, 1.0]]))
    assert not unitary(np.array([[1.0, 0.0], [1.0, 0.0]]))


def test_hermitian_identity_paulis_real_symmetric():
    assert hermitian(np.eye(2))
    assert hermitian(_X)
    assert hermitian(_Z)


def test_hermitian_pauli_y():
    assert hermitian(_Y)


def test_hermitian_general_complex():
    rng = np.random.default_rng(1)
    a = rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3))
    h = a + a.conjugate().T
    assert hermitian(h)


def test_hermitian_false_for_non_hermitian():
    assert not hermitian(np.array([[1.0 + 2j, 0.0], [0.0, 0.0]]))
    assert not hermitian(np.array([[0.0, 1.0], [2.0, 0.0]]))


@pytest.mark.parametrize(
    "matrices, expected_shape",
    [
        ([_X], (2, 2)),
        ([_X, _Y], (4, 4)),
        ([_Z, _HAD, np.eye(2)], (8, 8)),
    ],
)
def test_tensor_shape_and_matches_kron_chain(matrices, expected_shape):
    out = tensor(matrices)
    assert out.shape == expected_shape
    ref = matrices[0]
    for m in matrices[1:]:
        ref = np.kron(ref, m)
    assert np.allclose(out, ref)


def test_tensor_two_qubits_pauli_product():
    out = tensor([_Z, _X])
    assert np.allclose(out, np.kron(_Z, _X))


def test_tensor_three_single_qubits():
    a, b = np.array([1.0, 2.0]), np.array([-1j, 1.0])
    c = np.array([3.0, 4.0])
    out = tensor([a, b, c])
    assert np.allclose(out, np.kron(np.kron(a, b), c))


def test_positive_semidefinite_true_cases():
    assert positive_semidefinite(np.eye(3))
    assert positive_semidefinite(np.diag([0.0, 1.0, 4.0]))


def test_positive_semidefinite_false_for_indefinite_matrix():
    assert not positive_semidefinite(np.diag([-1.0, 2.0]))


def test_positive_definite_true_cases():
    assert positive_definite(np.eye(3))
    assert positive_definite(np.diag([0.5, 1.0, 4.0]))


def test_positive_definite_false_with_zero_or_negative_eigenvalue():
    assert not positive_definite(np.diag([0.0, 1.0, 2.0]))
    assert not positive_definite(np.diag([-1.0, 2.0]))


def test_negative_semidefinite_true_cases():
    assert negative_semidefinite(-np.eye(3))
    assert negative_semidefinite(np.diag([-4.0, -1.0, 0.0]))


def test_negative_definite_true_cases():
    assert negative_definite(-np.eye(3))
    assert negative_definite(np.diag([-4.0, -1.0, -0.5]))


def test_negative_definite_false_with_zero_or_positive_eigenvalue():
    assert not negative_definite(np.diag([-2.0, -1.0, 0.0]))
    assert not negative_definite(np.diag([-1.0, 2.0]))


def test_negative_semidefinite_false_for_indefinite_matrix():
    assert not negative_semidefinite(np.diag([-1.0, 2.0]))


def test_indefinite_true_for_mixed_sign_spectrum():
    assert indefinite(np.diag([-2.0, 0.0, 3.0]))


def test_indefinite_false_for_semidefinite_matrices():
    assert not indefinite(np.diag([0.0, 1.0, 2.0]))
    assert not indefinite(np.diag([-2.0, -1.0, 0.0]))
