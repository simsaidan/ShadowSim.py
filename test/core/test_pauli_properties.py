"""Property catalog: ``Pauli`` algebra.

Invariants exercised by Hypothesis tests in this module:

* Multiplication is associative up to phase × label.
* ``multiply`` agrees with dense matrix products (``phase * R.matrix()``).
* ``commutator`` matches ``P @ Q - Q @ P``; ``(None, None)`` iff matrices commute.
* Every Pauli matrix is Hermitian.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given
from strategies.pauli_random import ATOL, RTOL, paulis

from shadowsim.core import Pauli
from shadowsim.utils.hermitian import hermitian


@given(paulis(), paulis(), paulis())
def test_pauli_multiply_associative(p: Pauli, q: Pauli, r: Pauli):
    pq_phase, pq = p.multiply(q)
    left_phase, left = pq.multiply(r)
    left_phase *= pq_phase

    qr_phase, qr = q.multiply(r)
    right_phase, right = p.multiply(qr)
    right_phase *= qr_phase

    assert left == right
    assert left_phase == right_phase


@given(paulis(), paulis())
def test_pauli_multiply_matches_matrix_product(p: Pauli, q: Pauli):
    phase, result = p.multiply(q)
    expected = p.matrix() @ q.matrix()
    assert np.allclose(phase * result.matrix(), expected, atol=ATOL, rtol=RTOL)


@given(paulis(), paulis())
def test_pauli_commutator_matches_matrix_commutator(p: Pauli, q: Pauli):
    coeff, result = p.commutator(q)
    matrix_comm = p.matrix() @ q.matrix() - q.matrix() @ p.matrix()
    if coeff is None:
        assert result is None
        assert np.allclose(matrix_comm, 0.0, atol=ATOL, rtol=RTOL)
    else:
        assert result is not None
        assert np.allclose(coeff * result.matrix(), matrix_comm, atol=ATOL, rtol=RTOL)


@given(paulis())
def test_pauli_matrix_is_hermitian(p: Pauli):
    assert hermitian(p.matrix())


@given(paulis())
def test_pauli_squares_to_identity_up_to_phase(p: Pauli):
    phase, result = p.multiply(p)
    assert result == Pauli("I")
    assert abs(phase) == 1.0
