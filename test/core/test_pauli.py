"""Tests for src.core.pauli."""

import numpy as np
import pytest

from src.core.pauli import Pauli


def test_pauli_normalizes_and_exposes_label():
    pauli = Pauli("x")
    assert pauli.label == "X"
    assert str(pauli) == "X"
    assert repr(pauli) == "Pauli('X')"


def test_pauli_rejects_invalid_label():
    with pytest.raises(ValueError, match="invalid Pauli label"):
        Pauli("A")


def test_pauli_matrix_returns_copy():
    pauli = Pauli("Z")
    matrix = pauli.matrix()
    assert np.allclose(matrix, np.diag([1, -1]))
    matrix[0, 0] = 0
    assert pauli.matrix()[0, 0] == 1


def test_pauli_multiply_and_commutator():
    phase, result = Pauli("X").multiply(Pauli("Y"))
    assert phase == 1j
    assert result == Pauli("Z")

    coefficient, commutator = Pauli("X").commutator(Pauli("Y"))
    assert coefficient == 2j
    assert commutator == Pauli("Z")


def test_pauli_commutator_returns_none_for_commuting_pair():
    assert Pauli("X").commutator(Pauli("X")) == (None, None)
