"""Property catalog: ``PauliString`` algebra.

Invariants exercised by Hypothesis tests in this module:

* ``matrix()`` equals the Kronecker product of single-qubit Paulis in string order.
* ``multiply`` / ``commutator`` agree with dense matrix arithmetic (n ≤ 4).
* Commutator vanishes iff an even number of qubit positions anticommute.
"""

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from strategies.pauli_random import ATOL, MAX_PROPERTY_QUBITS, RTOL, pauli_words

from shadowsim.core import Pauli, PauliString
from shadowsim.core.pauli import _single_qubit_anticommutes
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.tensor import tensor


@st.composite
def _paired_strings(draw: st.DrawFn) -> tuple[PauliString, PauliString]:
    word = draw(pauli_words(min_n=1, max_n=MAX_PROPERTY_QUBITS))
    other = "".join(draw(st.sampled_from("IXYZ")) for _ in word)
    return PauliString.from_string(word), PauliString.from_string(other)


@given(pauli_words())
def test_pauli_string_matrix_matches_kronecker_chain(word: str):
    ps = PauliString.from_string(word)
    expected = tensor([Pauli(ch).matrix() for ch in word])
    assert np.allclose(ps.matrix(), expected, atol=ATOL, rtol=RTOL)


@given(_paired_strings())
def test_pauli_string_multiply_matches_matrix_product(pair: tuple[PauliString, PauliString]):
    left, right = pair
    phase, result = left.multiply(right)
    expected = left.matrix() @ right.matrix()
    assert np.allclose(phase * result.matrix(), expected, atol=ATOL, rtol=RTOL)


@given(_paired_strings())
def test_pauli_string_commutator_matches_matrix_and_parity(pair: tuple[PauliString, PauliString]):
    left, right = pair
    anticommuting = sum(1 for a, b in zip(str(left), str(right), strict=True) if _single_qubit_anticommutes(a, b))
    coeff, result = left.commutator(right)
    matrix_comm = left.matrix() @ right.matrix() - right.matrix() @ left.matrix()

    if anticommuting % 2 == 0:
        assert coeff is None and result is None
        assert np.allclose(matrix_comm, 0.0, atol=ATOL, rtol=RTOL)
    else:
        assert coeff is not None and result is not None
        assert np.allclose(coeff * result.matrix(), matrix_comm, atol=ATOL, rtol=RTOL)


@given(pauli_words())
def test_pauli_string_matrix_is_hermitian(word: str):
    assert hermitian(PauliString.from_string(word).matrix())
