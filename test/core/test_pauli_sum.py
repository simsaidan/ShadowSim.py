import numpy as np
import pytest

from shadowsim.core import Pauli, PauliString, PauliSum, parse_pauli_expression


def test_parse_single_pauli_word():
    ps = parse_pauli_expression("x i i")
    assert ps.terms == {"XII": 1 + 0j}
    assert ps.num_qubits == 3
    assert str(ps) == "XII"


def test_parse_sum_and_weighted_difference():
    ps = parse_pauli_expression("XXI + XYZ")
    assert ps.terms == {"XXI": 1 + 0j, "XYZ": 1 + 0j}
    assert str(ps) == "XXI + XYZ"

    weighted = parse_pauli_expression("0.5*XXI - XYZ")
    assert weighted.terms["XXI"] == pytest.approx(0.5 + 0j)
    assert weighted.terms["XYZ"] == pytest.approx(-1 + 0j)
    assert str(weighted) == "0.5*XXI - XYZ"


def test_parse_complex_coefficient():
    ps = parse_pauli_expression("-1+0.5j*XX")
    assert ps.terms == {"XX": -1 + 0.5j}
    assert not ps.is_hermitian()

    pure_imag = parse_pauli_expression("1j*X")
    assert pure_imag.terms == {"X": 1j}


def test_parse_combines_like_terms():
    ps = parse_pauli_expression("XII + XII - 0.5*XII")
    assert ps.terms == {"XII": 1.5 + 0j}


def test_parse_rejects_empty_unequal_and_trailing():
    with pytest.raises(ValueError, match="empty Pauli expression"):
        parse_pauli_expression("  ")
    with pytest.raises(ValueError, match="same length"):
        parse_pauli_expression("X + XX")
    with pytest.raises(ValueError, match="expected"):
        parse_pauli_expression("XXI +")
    with pytest.raises(ValueError, match="zero operator"):
        parse_pauli_expression("X - X")


def test_pauli_sum_from_pauli_string_and_matrix():
    one = PauliSum.from_pauli_string(PauliString.from_string("XZ"), coeff=2)
    assert one.terms == {"XZ": 2 + 0j}
    expected = 2 * np.kron(Pauli("X").matrix(), Pauli("Z").matrix())
    assert np.allclose(one.to_matrix(), expected)

    summed = PauliSum.from_string("XXI + XYZ")
    hand = PauliString.from_string("XXI").matrix() + PauliString.from_string("XYZ").matrix()
    assert np.allclose(summed.to_matrix(), hand)


def test_pauli_sum_hermitian_and_equality():
    h = PauliSum({"XII": 1.0, "ZII": -0.5})
    assert h.is_hermitian()
    assert h == PauliSum.from_string("XII - 0.5*ZII")
    assert h != PauliSum.from_string("XII")
    assert h.__eq__("XII") is NotImplemented


def test_pauli_sum_rejects_invalid_construction():
    with pytest.raises(ValueError, match="at least one term"):
        PauliSum({})
    with pytest.raises(ValueError, match="invalid Pauli word"):
        PauliSum({"XA": 1})
    with pytest.raises(ValueError, match="same length"):
        PauliSum({"X": 1, "XX": 1})
    with pytest.raises(TypeError, match="Pauli label must be a string"):
        PauliSum([(1, 1.0)])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="at least one term"):
        PauliSum([("X", 1.0), ("X", -1.0)])


def test_pauli_sum_iterable_merge_len_and_repr():
    ps = PauliSum([("X", 0.5), ("X", 0.5), ("Y", -2.0)])
    assert ps.terms == {"X": 1.0 + 0j, "Y": -2.0 + 0j}
    assert len(ps) == 2
    assert "PauliSum(" in repr(ps)


def test_pauli_sum_format_imag_and_complex_coeffs():
    assert str(PauliSum({"X": 1j})) == "1j*X"
    assert str(PauliSum({"X": -1j})) == "-1j*X"
    assert str(PauliSum({"X": 2j, "Y": -3j})) == "2j*X - 3j*Y"

    general = str(PauliSum({"X": 1 + 2j}))
    assert general.endswith("*X")
    assert "1" in general and "2j" in general

    negative_general = str(PauliSum({"X": -1 + 0.5j}))
    assert negative_general.startswith("-")
    assert negative_general.endswith("*X")


def test_parse_coeff_without_star_and_missing_separator():
    assert parse_pauli_expression("2XX").terms == {"XX": 2 + 0j}
    with pytest.raises(ValueError, match=r"expected '\+' or '-'"):
        parse_pauli_expression("XX#YY")
