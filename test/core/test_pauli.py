"""Tests for shadowsim.core.pauli."""

import numpy as np
import pytest

from shadowsim.core import Pauli
from shadowsim.core import pauli as pauli_module


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


def test_pauli_eq_returns_notimplemented_for_other_types():
    assert Pauli("X").__eq__("X") is NotImplemented


def test_pauli_multiply_labels_unreachable_raises(monkeypatch):
    monkeypatch.setattr(
        pauli_module,
        "_PAULI_MATRICES",
        {
            "I": np.zeros((2, 2), dtype=np.complex128),
            "X": np.array([[1, 2], [3, 4]], dtype=np.complex128),
            "Y": np.array([[5, 6], [7, 8]], dtype=np.complex128),
            "Z": np.array([[9, 0], [0, 1]], dtype=np.complex128),
        },
    )
    with pytest.raises(RuntimeError, match="unreachable"):
        pauli_module._multiply_labels("X", "Y")
