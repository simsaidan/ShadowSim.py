"""Tests for the quadratic shadow change of basis."""

import numpy as np
import pytest

from shadowsim.shadow import ChangeOfBasis, change_of_basis
from shadowsim.utils.hermitian import hermitian


def _canonical_omega(num_oscillators: int) -> np.ndarray:
    identity = np.eye(num_oscillators)
    zeros = np.zeros((num_oscillators, num_oscillators))
    return np.block([[zeros, -identity], [identity, zeros]])


def _assert_relations(gamma: np.ndarray, result: ChangeOfBasis) -> None:
    assert isinstance(result, ChangeOfBasis)
    assert hermitian(result.H_S)
    assert np.allclose(result.A, result.B.conj().T)
    assert np.allclose(result.B @ result.B.conj().T, gamma)
    assert np.allclose(result.H_S, 1j * result.B.conj().T @ result.omega @ result.B)
    assert np.allclose(result.quadrature_H_S, 1j * result.omega @ gamma)


def test_one_oscillator_quadrature_matrix_is_not_hermitian():
    """Mass m = 1 and spring κ = 2: iΩΓ is not Hermitian and H_S is."""
    gamma = np.diag([1.0, 2.0])
    result = change_of_basis(gamma)

    _assert_relations(gamma, result)
    assert hermitian(result.quadrature_H_S) is False
    assert np.allclose(result.omega, _canonical_omega(1))
    assert np.allclose(result.H_S, result.A @ result.quadrature_H_S @ np.linalg.inv(result.A))


def test_two_oscillator_coupled_gamma():
    """An off-diagonal positive-definite Γ on two oscillators uses the same relations."""
    gamma = np.array(
        [
            [2.0, 0.3, 0.0, 0.1],
            [0.3, 1.5, 0.2, 0.0],
            [0.0, 0.2, 2.5, -0.4],
            [0.1, 0.0, -0.4, 1.2],
        ]
    )
    result = change_of_basis(gamma)

    _assert_relations(gamma, result)
    assert result.H_S.shape == (4, 4)
    assert hermitian(result.quadrature_H_S) is False
    assert np.allclose(result.omega, _canonical_omega(2))
    assert np.allclose(result.H_S, result.A @ result.quadrature_H_S @ np.linalg.inv(result.A))


def test_singular_gamma_is_factored_without_cholesky():
    """A zero eigenvalue is positive semidefinite, so Cholesky rejects it and eigh does not."""
    gamma = np.diag([1.0, 0.0])
    with pytest.raises(np.linalg.LinAlgError):
        np.linalg.cholesky(gamma)

    result = change_of_basis(gamma)

    _assert_relations(gamma, result)
    assert hermitian(result.quadrature_H_S) is False


def test_custom_skew_omega_hermitizes_shadow_matrix():
    """A caller-supplied real skew Ω, including odd dimension, uses H_S = i B† Ω B."""
    gamma = np.diag([1.0, 2.0, 3.0])
    omega = np.array(
        [
            [0.0, 1.0, -1.0],
            [-1.0, 0.0, 2.0],
            [1.0, -2.0, 0.0],
        ]
    )
    result = change_of_basis(gamma, omega)

    _assert_relations(gamma, result)
    assert np.allclose(result.omega, omega)
    assert hermitian(result.quadrature_H_S) is False
    assert np.allclose(result.H_S, result.A @ result.quadrature_H_S @ np.linalg.inv(result.A))


def test_change_of_basis_clips_tiny_negative_eigenvalue():
    gamma = np.diag([1.0, -1e-12])
    result = change_of_basis(gamma)

    assert hermitian(result.H_S)
    assert np.allclose(result.B @ result.B.conj().T, np.diag([1.0, 0.0]))


def test_change_of_basis_accepts_negligible_imaginary_part():
    gamma = np.diag([1.0, 2.0]).astype(np.complex128)
    gamma[0, 1] = 1e-16
    gamma[1, 0] = 1e-16
    result = change_of_basis(gamma)

    _assert_relations(np.real(gamma), result)


def test_change_of_basis_rejects_non_square_gamma():
    with pytest.raises(ValueError, match="square matrix"):
        change_of_basis([1.0, 2.0])
    with pytest.raises(ValueError, match="square matrix"):
        change_of_basis(np.ones((2, 3)))


def test_change_of_basis_rejects_non_symmetric_gamma():
    gamma = np.array([[1.0, 2.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match="symmetric"):
        change_of_basis(gamma)


def test_change_of_basis_rejects_non_real_gamma():
    gamma = np.array([[1.0, 1j], [-1j, 1.0]])
    with pytest.raises(ValueError, match="must be real"):
        change_of_basis(gamma)


def test_change_of_basis_rejects_indefinite_gamma():
    with pytest.raises(ValueError, match="positive semidefinite"):
        change_of_basis(np.diag([1.0, -1.0]))


def test_change_of_basis_rejects_odd_dimension_without_omega():
    with pytest.raises(ValueError, match="even-dimensional"):
        change_of_basis(np.eye(3))


def test_change_of_basis_rejects_bad_omega():
    gamma = np.eye(2)
    with pytest.raises(ValueError, match="skew-symmetric"):
        change_of_basis(gamma, np.eye(2))
    with pytest.raises(ValueError, match=r"shape \(4, 4\)"):
        change_of_basis(np.eye(4), np.array([[0.0, -1.0], [1.0, 0.0]]))
    with pytest.raises(ValueError, match="must be real"):
        change_of_basis(gamma, np.array([[0.0, -1j], [1j, 0.0]]))
    with pytest.raises(ValueError, match="square matrix"):
        change_of_basis(gamma, [0.0, -1.0])
