"""Change of basis that Hermitizes a quadratic shadow Hamiltonian.

Somma et al. (arXiv:2407.21775, Sec. 2) write ``H = (1/2) Y^T Γ Y`` for
operators with ``[Y_j, Y_k] = i Ω_jk``. In that basis the shadow matrix is
``i Ω Γ``, which is not Hermitian in general. A factor ``Γ = B B†`` with
``A = B†`` produces ``H_S = i B† Ω B``, which is Hermitian when ``Ω`` is real
and skew-symmetric. Canonical oscillator quadratures are the default ``Ω``.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

# Match the eigenvalue tolerance used for positive-semidefinite checks.
_EIG_ATOL = 1e-10


@dataclass(frozen=True)
class ChangeOfBasis:
    """Factors and shadow matrices for a quadratic change of basis.

    Attributes:
        A: Change-of-basis matrix ``A = B†``. New operators are ``O = A Y``.
        B: Factor with ``Γ = B B†``.
        H_S: Shadow matrix ``i B† Ω B`` in the new basis.
        quadrature_H_S: Shadow matrix ``i Ω Γ`` before the change of basis.
        omega: Commutator matrix used, with ``[Y_j, Y_k] = i Ω_jk``.
    """

    A: npt.NDArray[np.complexfloating]
    B: npt.NDArray[np.complexfloating]
    H_S: npt.NDArray[np.complexfloating]
    quadrature_H_S: npt.NDArray[np.complexfloating]
    omega: npt.NDArray[np.floating]


def change_of_basis(
    gamma: npt.ArrayLike,
    omega: npt.ArrayLike | None = None,
) -> ChangeOfBasis:
    """Return a change of basis that Hermitizes a quadratic shadow matrix.

    ``gamma`` is the real symmetric positive-semidefinite matrix ``Γ`` in
    ``H = (1/2) Y^T Γ Y``. ``omega`` is the real skew-symmetric commutator
    matrix in ``[Y_j, Y_k] = i Ω_jk``. When ``omega`` is omitted it is the
    canonical quadrature matrix for ``n`` oscillators,

    ``Ω = [[0, -I], [I, 0]]``,

    and ``Γ`` must have even shape ``(2n, 2n)``. The factor ``B`` comes from
    the symmetric eigendecomposition, so a singular ``Γ`` is allowed.

    Args:
        gamma: Real symmetric positive-semidefinite matrix ``Γ``.
        omega: Real skew-symmetric commutator matrix. Defaults to the
            canonical quadrature matrix of matching even dimension.

    Returns:
        Factors ``A = B†`` and ``B``, the Hermitian shadow matrix
        ``H_S = i B† Ω B``, the quadrature shadow matrix ``i Ω Γ``, and the
        ``Ω`` that was used.

    Raises:
        ValueError: If ``gamma`` is not real symmetric or not positive
            semidefinite, if ``omega`` is omitted and ``gamma`` has odd
            dimension, or if ``omega`` is not real, skew-symmetric, and the
            same shape as ``gamma``.

    Examples:
        One oscillator with mass ``m = 1`` and spring ``κ = 2`` has
        ``Γ = diag(1, 2)``. The quadrature shadow matrix is not Hermitian;
        the returned ``H_S`` is:

        ```python exec="1" source="above" result="text"
        import numpy as np
        from shadowsim.shadow import change_of_basis
        from shadowsim.utils.hermitian import hermitian

        basis = change_of_basis(np.diag([1.0, 2.0]))
        print(hermitian(basis.quadrature_H_S), hermitian(basis.H_S))
        ```

    """
    gamma_matrix = _real_symmetric(gamma, name="gamma")
    omega_matrix = _commutator_matrix(omega, gamma_matrix.shape[0])
    factor = _psd_factor(gamma_matrix)
    transformed = factor.conj().T
    return ChangeOfBasis(
        A=transformed,
        B=factor,
        H_S=1j * (transformed @ omega_matrix @ factor),
        quadrature_H_S=1j * (omega_matrix @ gamma_matrix),
        omega=omega_matrix,
    )


def _real_square(matrix: npt.ArrayLike, *, name: str) -> npt.NDArray[np.float64]:
    """Return ``matrix`` as a real square float64 array."""
    array = np.asarray(matrix)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError(f"{name} must be a square matrix, got shape {array.shape}")
    if np.iscomplexobj(array) and not np.allclose(np.imag(array), 0.0, atol=_EIG_ATOL, rtol=0.0):
        raise ValueError(f"{name} must be real")
    return np.real(array).astype(np.float64, copy=False)


def _real_symmetric(matrix: npt.ArrayLike, *, name: str) -> npt.NDArray[np.float64]:
    """Return ``matrix`` when it is real and symmetric."""
    real = _real_square(matrix, name=name)
    if not np.allclose(real, real.T, atol=_EIG_ATOL, rtol=0.0):
        raise ValueError(f"{name} must be symmetric")
    return real


def _commutator_matrix(omega: npt.ArrayLike | None, dimension: int) -> npt.NDArray[np.float64]:
    """Return a real skew-symmetric commutator matrix of shape ``(dimension, dimension)``."""
    if omega is None:
        if dimension % 2 != 0:
            raise ValueError(
                f"gamma must be even-dimensional when omega is omitted, got shape {(dimension, dimension)}"
            )
        return _canonical_omega(dimension // 2)
    real = _real_square(omega, name="omega")
    if real.shape != (dimension, dimension):
        raise ValueError(f"omega must have shape {(dimension, dimension)}, got {real.shape}")
    if not np.allclose(real, -real.T, atol=_EIG_ATOL, rtol=0.0):
        raise ValueError("omega must be skew-symmetric")
    return real


def _canonical_omega(num_oscillators: int) -> npt.NDArray[np.float64]:
    """Return ``Ω = [[0, -I], [I, 0]]`` for ``num_oscillators`` modes."""
    identity = np.eye(num_oscillators, dtype=np.float64)
    zeros = np.zeros_like(identity)
    return np.block([[zeros, -identity], [identity, zeros]])


def _psd_factor(gamma: npt.NDArray[np.float64]) -> npt.NDArray[np.complex128]:
    """Return ``B`` with ``Γ = B B†`` from the symmetric eigendecomposition.

    Eigenvalues in ``[-_EIG_ATOL, 0)`` are clipped to zero. A more negative
    eigenvalue means ``Γ`` is not positive semidefinite.
    """
    eigenvalues, eigenvectors = np.linalg.eigh(gamma)
    if np.any(eigenvalues < -_EIG_ATOL):
        raise ValueError("gamma must be positive semidefinite")
    scale = np.sqrt(np.maximum(eigenvalues, 0.0))
    return (eigenvectors * scale).astype(np.complex128, copy=False)
