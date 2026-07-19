import numpy as np
import pytest

from shadowsim.core import Pauli
from shadowsim.core import PauliString


def test_pauli_string_from_string_and_protocols():
    pauli_string = PauliString.from_string("x y z")
    assert str(pauli_string) == "XYZ"
    assert repr(pauli_string) == "PauliString(['X', 'Y', 'Z'])"
    assert len(pauli_string) == 3
    assert pauli_string.num_qubits == 3
    assert pauli_string.paulis == (Pauli("X"), Pauli("Y"), Pauli("Z"))


def test_pauli_string_rejects_empty_input():
    with pytest.raises(ValueError, match="empty Pauli string"):
        PauliString.from_string(" ")
    with pytest.raises(ValueError, match="must contain at least one Pauli"):
        PauliString([])


def test_pauli_string_matrix_uses_string_order():
    pauli_string = PauliString.from_string("XZ")
    expected = np.kron(Pauli("X").matrix(), Pauli("Z").matrix())
    assert np.allclose(pauli_string.matrix(), expected)


def test_pauli_string_multiply_and_commutator():
    left = PauliString.from_string("XI")
    right = PauliString.from_string("YI")

    phase, product = left.multiply(right)
    assert phase == 1j
    assert product == PauliString.from_string("ZI")

    coefficient, commutator = left.commutator(right)
    assert coefficient == 2j
    assert commutator == PauliString.from_string("ZI")


def test_pauli_string_commutator_returns_none_for_even_anticommutations():
    left = PauliString.from_string("XX")
    right = PauliString.from_string("YY")
    assert left.commutator(right) == (None, None)


def test_pauli_string_rejects_length_mismatch():
    short = PauliString.from_string("X")
    long = PauliString.from_string("XX")
    with pytest.raises(ValueError, match="length mismatch"):
        short.multiply(long)
    with pytest.raises(ValueError, match="length mismatch"):
        short.commutator(long)
