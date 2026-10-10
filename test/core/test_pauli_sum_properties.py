"""Property catalog: ``PauliSum`` linear combinations.

Invariants exercised by Hypothesis tests in this module:

* ``(A + B).to_matrix()`` equals ``A.to_matrix() + B.to_matrix()`` (n ≤ 4).
* Real coefficients imply a Hermitian matrix and ``is_hermitian()`` is true.
* Parse / construct round-trips preserve merged terms for generated expressions.
"""

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL, real_pauli_sums

from shadowsim.core import PauliSum, parse_pauli_expression
from shadowsim.utils.hermitian import hermitian


@st.composite
def _same_n_real_sums(draw: st.DrawFn) -> tuple[PauliSum, PauliSum]:
    n = draw(st.integers(min_value=1, max_value=MAX_PROPERTY_QUBITS))
    a = draw(real_pauli_sums(min_n=n, max_n=n))
    b = draw(real_pauli_sums(min_n=n, max_n=n))
    return a, b


@given(_same_n_real_sums())
def test_pauli_sum_add_matches_matrix_sum(pair: tuple[PauliSum, PauliSum]):
    a, b = pair
    expected = a.to_matrix() + b.to_matrix()
    if np.allclose(expected, 0.0, atol=ATOL, rtol=RTOL):
        try:
            _ = a + b
        except ValueError as exc:
            assert "at least one term" in str(exc)
            return
    summed = a + b
    assert np.allclose(summed.to_matrix(), expected, atol=ATOL, rtol=RTOL)


@given(real_pauli_sums())
def test_real_pauli_sum_is_hermitian(ps: PauliSum):
    assert ps.is_hermitian()
    assert hermitian(ps.to_matrix())


@given(real_pauli_sums())
def test_pauli_sum_str_parse_round_trip(ps: PauliSum):
    parsed = parse_pauli_expression(str(ps))
    assert parsed == ps
