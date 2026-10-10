"""Property catalog: matrix utility predicates and Kronecker products.

Invariants exercised by Hypothesis tests in this module:

* ``hermitian(H)`` iff ``H == H.conj().T`` on small random matrices.
* ``unitary(U)`` iff ``U @ U.conj().T == I`` on small random unitaries.
* ``tensor(factors)`` equals a chained ``np.kron`` of the same factors.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, RTOL

from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.tensor import tensor
from shadowsim.utils.unitary import unitary

_MAX_DIM = 8
_MAX_FACTORS = 3


@st.composite
def _complex_matrices(draw: st.DrawFn, *, dim: int | None = None) -> np.ndarray:
    n = dim if dim is not None else draw(st.integers(min_value=1, max_value=_MAX_DIM))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))


@st.composite
def _hermitian_matrices(draw: st.DrawFn) -> np.ndarray:
    a = draw(_complex_matrices())
    return a + a.conjugate().T


@st.composite
def _unitary_matrices(draw: st.DrawFn) -> np.ndarray:
    a = draw(_complex_matrices())
    q, _ = np.linalg.qr(a)
    # QR phases are not unique; normalize diagonal phases for a clean unitary.
    phases = np.diag(q)
    phases = phases / np.where(np.abs(phases) < 1e-15, 1.0, np.abs(phases))
    return q @ np.diag(np.conjugate(phases))


@st.composite
def _factor_lists(draw: st.DrawFn) -> list[np.ndarray]:
    n_factors = draw(st.integers(min_value=1, max_value=_MAX_FACTORS))
    factors: list[np.ndarray] = []
    for _ in range(n_factors):
        dim = draw(st.integers(min_value=1, max_value=3))
        factors.append(draw(_complex_matrices(dim=dim)))
    return factors


@given(_hermitian_matrices())
def test_hermitian_true_for_constructed_hermitian(h: np.ndarray):
    assert hermitian(h)
    assert np.allclose(h, h.conjugate().T, atol=ATOL, rtol=RTOL)


@given(_complex_matrices())
def test_hermitian_false_when_not_equal_adjoint(a: np.ndarray):
    # Force a non-Hermitian case when possible; skip pure-Hermitian draws.
    if np.allclose(a, a.conjugate().T, atol=ATOL, rtol=RTOL):
        a = a + 1j * np.eye(a.shape[0])
    assert not hermitian(a)


@given(_unitary_matrices())
def test_unitary_true_for_qr_unitaries(u: np.ndarray):
    assert unitary(u)
    assert np.allclose(u @ u.conjugate().T, np.eye(u.shape[0]), atol=ATOL, rtol=RTOL)


@given(_complex_matrices())
def test_unitary_false_for_generic_matrices(a: np.ndarray):
    if np.allclose(a @ a.conjugate().T, np.eye(a.shape[0]), atol=ATOL, rtol=RTOL):
        a = a + np.eye(a.shape[0])
    assert not unitary(a)


@given(_factor_lists())
def test_tensor_matches_chained_kron(factors: list[np.ndarray]):
    expected = factors[0]
    for mat in factors[1:]:
        expected = np.kron(expected, mat)
    assert np.allclose(tensor(factors), expected, atol=ATOL, rtol=RTOL)
