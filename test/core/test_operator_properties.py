"""Property catalog: ``Operator`` dual representations.

Invariants exercised by Hypothesis tests in this module:

* Pauli-backed and densified constructors agree on ``matrix`` (n ≤ 4).
* Hermitian / unitary / definiteness flags match ``shadowsim.utils`` predicates.
* Equality is consistent with numerical matrix agreement.
"""

import numpy as np
from hypothesis import given
from strategies.pauli_random import ATOL, RTOL, real_pauli_sums

from shadowsim.core import Operator, PauliSum
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.indefinite import indefinite
from shadowsim.utils.negative_semidefinite import negative_semidefinite
from shadowsim.utils.positive_semidefinite import positive_semidefinite
from shadowsim.utils.unitary import unitary


@given(real_pauli_sums())
def test_operator_pauli_and_dense_constructors_agree(ps: PauliSum):
    sparse = Operator(ps)
    dense = Operator(ps.to_matrix())
    assert sparse.pauli_sum is not None
    assert dense.pauli_sum is None
    assert np.allclose(sparse.matrix, dense.matrix, atol=ATOL, rtol=RTOL)
    assert sparse == dense


@given(real_pauli_sums())
def test_operator_lazy_hermitian_matches_pauli_sum_and_matrix(ps: PauliSum):
    op = Operator(ps)
    assert op.is_hermitian is True
    assert op._matrix_cache is None
    assert hermitian(op.matrix)
    assert op.is_hermitian is True


@given(real_pauli_sums())
def test_operator_flags_match_utils_after_densify(ps: PauliSum):
    op = Operator(ps)
    matrix = op.matrix
    assert op.is_hermitian == hermitian(matrix)
    assert op.is_unitary == unitary(matrix)
    assert op.is_positive_semidefinite == positive_semidefinite(matrix)
    assert op.is_negative_semidefinite == negative_semidefinite(matrix)
    assert op.is_indefinite == indefinite(matrix)


@given(real_pauli_sums())
def test_operator_complex_coeff_not_lazy_hermitian(ps: PauliSum):
    terms = {lab: complex(coeff) + 1j for lab, coeff in ps.terms.items()}
    complex_ps = PauliSum(terms)
    op = Operator(complex_ps)
    assert complex_ps.is_hermitian() is False
    assert op.is_hermitian is False
    assert op._matrix_cache is None
