"""Tests for the builder page's state, measurement, and action catalog."""

import math

import pytest

from shadowsim.cli.catalog import (
    action_record,
    labels_for,
    listed_actions,
    listed_measurements,
    listed_states,
    measurement_record,
    measurements_for,
    observables_for,
    prepare_state,
)
from shadowsim.core.operator import Operator
from shadowsim.simulators.reducers import Measurement


def test_listed_states_describe_the_four_encodings() -> None:
    listed = listed_states()
    assert [item["id"] for item in listed] == ["basis", "gray", "angle", "amplitude"]
    basis, gray, angle, amplitude = (item["field"] for item in listed)
    assert basis == {
        "kind": "bits",
        "label": "Bits",
        "aria": "Basis bits",
        "cap": 15,
        "encode": "ComputationalBasisEncoding",
        "display": "ket",
        "empty": "Enter a bit string",
        "mismatch": "Must be {n} bits.",
        "size": "Enter a {n}-bit basis string",
        "blank": "0s and 1s, up to {cap}",
    }
    assert gray["display"] == "gray"
    assert gray["encode"] == "GrayEncoding"
    assert gray["size"] == "Enter a {n}-bit Gray code string"
    assert angle["kind"] == "numbers"
    assert angle["match"] == "length"
    assert angle["nonzero"] is False
    assert angle["unit"] == "angle"
    assert angle["encode"] == "AngleEncoding"
    assert angle["cap"] == 15
    assert amplitude["match"] == "padded"
    assert amplitude["nonzero"] is True
    assert amplitude["unit"] == "qubit"
    assert amplitude["cap"] == 16
    assert amplitude["encode"] == "AmplitudeEncoding"
    assert listed[0]["title"] == "Basis state"
    assert listed[0]["phrase"] == "Basis state"


def test_listed_measurements_name_pauli_and_counts() -> None:
    listed = listed_measurements()
    assert [item["id"] for item in listed] == ["z", "x", "counts"]
    assert listed[0]["letter"] == "Z"
    assert listed[0]["rotate"] is False
    assert "field" not in listed[0]
    assert listed[1]["letter"] == "X"
    assert listed[1]["rotate"] is True
    assert listed[2]["kind"] == "counts"
    assert listed[2]["field"] == {"kind": "expression", "label": "Expression", "aria": "Counts expression"}
    assert "letter" not in listed[2]
    assert measurement_record("x")["rotate"] is True


def test_listed_actions_default_the_path_chips() -> None:
    listed = listed_actions()
    assert [item["id"] for item in listed] == ["plot", "save", "export"]
    assert "field" not in listed[0]
    assert listed[0]["phrase"] == "plot results"
    assert listed[1]["field"] == {
        "kind": "path",
        "key": "save_path",
        "default": "results/run1",
        "label": "Path",
        "aria": "Save path",
    }
    assert listed[2]["field"]["default"] == "results"
    assert listed[2]["field"]["key"] == "export_path"
    assert action_record("save")["field"]["aria"] == "Save path"


def test_prepare_state_encodes_a_basis_string() -> None:
    vector = prepare_state("basis", 2, "01").to_numpy().reshape(-1)
    assert vector.shape == (4,)
    assert vector[1] == 1
    assert prepare_state("basis", 15, "1" * 15).get_num_qubits() == 15


@pytest.mark.parametrize(
    ("basis", "qubits", "match"),
    [
        (None, 2, "basis bits"),
        ("", 2, "basis bits"),
        ("2", 2, "basis bits"),
        ("10 ", 2, "basis bits"),
        ("1" * 16, 16, "15"),
        ("101", 2, "basis bit string length must equal the qubit count"),
    ],
)
def test_prepare_state_rejects_a_bad_basis_string(basis: object, qubits: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        prepare_state("basis", qubits, basis)


def test_prepare_state_encodes_a_gray_string() -> None:
    vector = prepare_state("gray", 3, "101").to_numpy().reshape(-1)
    assert vector.shape == (8,)
    assert vector[7] == 1


def test_prepare_state_rejects_a_bad_gray_string() -> None:
    with pytest.raises(ValueError, match="Gray code bits"):
        prepare_state("gray", 3, "102")
    with pytest.raises(ValueError, match="Gray code bit string length must equal the qubit count"):
        prepare_state("gray", 2, "101")


def test_prepare_state_encodes_one_angle_per_qubit() -> None:
    vector = prepare_state("angle", 1, [math.pi / 2]).to_numpy().reshape(-1)
    assert vector[0] == pytest.approx(math.cos(math.pi / 4))
    assert vector[1] == pytest.approx(math.sin(math.pi / 4))
    assert prepare_state("angle", 2, [0, 1.5]).get_num_qubits() == 2


@pytest.mark.parametrize(
    "angles",
    [None, [], [0.0], [True, 0.0], ["0", 0.0], [math.inf, 0.0], [0.0, math.nan]],
)
def test_prepare_state_rejects_a_bad_angle_list(angles: object) -> None:
    with pytest.raises(ValueError, match="angles must be 2 finite real numbers"):
        prepare_state("angle", 2, angles)


def test_prepare_state_pads_amplitudes_to_the_model() -> None:
    assert prepare_state("amplitude", 2, [1.0, 0.5, 0.25]).get_num_qubits() == 2
    assert prepare_state("amplitude", 1, [1.0]).get_num_qubits() == 1
    assert prepare_state("amplitude", 5, [1.0] * 17).get_num_qubits() == 5


def test_prepare_state_rejects_amplitudes_that_do_not_match() -> None:
    with pytest.raises(ValueError, match="prepares 1 qubit, model has 2 qubits"):
        prepare_state("amplitude", 2, [1.0])
    with pytest.raises(ValueError, match="prepares 2 qubits, model has 1 qubit"):
        prepare_state("amplitude", 1, [1.0, 0.5, 0.25])
    with pytest.raises(ValueError, match="non-zero"):
        prepare_state("amplitude", 1, [0.0])
    with pytest.raises(ValueError, match="amplitudes must be a non-empty list"):
        prepare_state("amplitude", 1, [])
    with pytest.raises(ValueError, match="amplitudes must be a non-empty list"):
        prepare_state("amplitude", 1, "1")


def test_prepare_state_rejects_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown initial state"):
        prepare_state("nope", 2)


def test_measurements_for_reads_each_selected_qubit() -> None:
    assert measurements_for({"id": "z"}, 2) == [Measurement.expectation(0), Measurement.expectation(1)]
    assert measurements_for({"id": "x", "sites": [1, 1, 0]}, 2) == [
        Measurement.expectation(1),
        Measurement.expectation(0),
    ]
    counts = measurements_for({"id": "counts", "sites": [0], "expression": 'counts["0"] / shots'}, 1)
    assert counts == [Measurement((0,), 'counts["0"] / shots')]


def test_measurements_for_rejects_a_bad_selection() -> None:
    with pytest.raises(ValueError, match="unknown measurement"):
        measurements_for({"id": "y"}, 1)
    with pytest.raises(ValueError, match="unknown measurement"):
        measurements_for({"id": 1}, 1)
    with pytest.raises(ValueError, match="a counts measurement needs an expression"):
        measurements_for({"id": "counts"}, 1)
    with pytest.raises(ValueError, match="measured qubits must be a non-empty list"):
        measurements_for({"id": "z", "sites": []}, 1)
    with pytest.raises(ValueError, match="measured qubits must be a non-empty list"):
        measurements_for({"id": "z", "sites": "0"}, 1)


@pytest.mark.parametrize("sites", [[True], [1.5], [-1], [2], ["0"]])
def test_measurements_for_rejects_a_bad_index(sites: list[object]) -> None:
    with pytest.raises(ValueError, match="indexes from 0 to 1"):
        measurements_for({"id": "z", "sites": sites}, 2)


def test_labels_for_names_each_curve() -> None:
    assert labels_for({"id": "z", "sites": [0, 1]}, 2) == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    assert labels_for({"id": "x", "sites": [1]}, 2) == ["⟨X⟩ on 1"]
    counts = {"id": "counts", "sites": [0, 1], "expression": ' counts["01"] / shots '}
    assert labels_for(counts, 2) == ['counts["01"] / shots']


def test_labels_for_rejects_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown measurement"):
        labels_for({"id": "y", "sites": [0]}, 1)


def test_observables_for_places_the_pauli_letter() -> None:
    assert observables_for(2, "z", [0, 1]) == [Operator("ZI"), Operator("IZ")]
    assert observables_for(2, "x", [1]) == [Operator("IX")]
    with pytest.raises(ValueError, match="unknown measurement"):
        observables_for(1, "y", [0])
    with pytest.raises(ValueError, match="no Pauli operators"):
        observables_for(1, "counts", [0])


def test_records_reject_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown measurement"):
        measurement_record("y")
    with pytest.raises(ValueError, match="unknown action"):
        action_record("print")
