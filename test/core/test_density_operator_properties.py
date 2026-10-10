"""Property catalog: ``DensityOperator``.

Invariants exercised by Hypothesis tests in this module:

* ``from_state`` yields a rank-1 projector with trace 1 that is PSD.
* Convex combinations of pure states form valid density operators (small dim).
"""

from __future__ import annotations

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL, normalize_state_vector, normalized_states

from shadowsim.core import DensityOperator, State
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.positive_semidefinite import positive_semidefinite


@given(normalized_states())
def test_density_operator_from_state_is_pure_projector(sample: tuple[np.ndarray, int, int]):
    vec, n, local_dim = sample
    state = State(vec, num_qubits=n, local_dim=local_dim)
    rho = DensityOperator.from_state(state)

    ket = vec.reshape(-1, 1)
    expected = ket @ ket.conj().T
    assert np.allclose(rho.matrix, expected, atol=ATOL, rtol=RTOL)
    assert np.isclose(rho.trace(), 1.0)
    assert hermitian(rho.matrix)
    assert positive_semidefinite(rho.matrix)
    # Rank-1: ρ² = ρ
    assert np.allclose(rho.matrix @ rho.matrix, rho.matrix, atol=ATOL, rtol=RTOL)


@st.composite
def _mixed_states(draw: st.DrawFn) -> np.ndarray:
    n = draw(st.integers(min_value=1, max_value=min(3, MAX_PROPERTY_QUBITS)))
    k = draw(st.integers(min_value=1, max_value=4))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed)
    dim = 2**n
    weights = rng.random(k)
    weights = weights / weights.sum()
    rho = np.zeros((dim, dim), dtype=np.complex128)
    for w in weights:
        raw = rng.standard_normal(dim) + 1j * rng.standard_normal(dim)
        psi = normalize_state_vector(raw).reshape(-1, 1)
        rho += w * (psi @ psi.conj().T)
    # Numerical cleanup: enforce Hermiticity before validation.
    return 0.5 * (rho + rho.conjugate().T)


@given(_mixed_states())
def test_density_operator_accepts_mixed_states(rho: np.ndarray):
    # Renormalize trace in case of floating-point drift.
    rho = rho / np.trace(rho)
    op = DensityOperator(rho)
    assert np.isclose(op.trace(), 1.0)
    assert hermitian(op.matrix)
    assert positive_semidefinite(op.matrix)
