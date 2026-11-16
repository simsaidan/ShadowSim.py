"""Tests for Measurement and apply_measurements."""

import numpy as np
import pytest

from shadowsim.simulators import Measurement, SimulationResult, apply_measurements


def _result(counts: list[dict[str, int]] | None) -> SimulationResult:
    times = np.linspace(0.0, 1.0, 1 if counts is None else len(counts))
    return SimulationResult(
        times=times,
        observables=[np.zeros(len(times))],
        algorithm="demo",
        metadata={"num_qubits": 3},
        counts=counts,
    )


def test_measurement_reads_its_qubits_in_the_order_listed():
    counts = {"100": 3, "001": 1}
    assert Measurement((0,), 'counts["1"]').evaluate(counts) == 3.0
    assert Measurement((2, 0), 'counts["01"]').evaluate(counts) == 3.0
    assert Measurement((2, 0), 'counts["10"]').evaluate(counts) == 1.0


def test_measurement_sums_shots_that_differ_only_on_unread_qubits():
    same = Measurement((0, 1), '(counts["00"] + counts["11"]) / shots')
    assert same.evaluate({"000": 6, "110": 2, "011": 2}) == pytest.approx(0.8)


def test_measurement_treats_a_missing_bitstring_as_zero():
    assert Measurement((0,), 'counts["1"] / shots').evaluate({"0": 4}) == 0.0


def test_measurement_supports_arithmetic():
    counts = {"0": 3, "1": 1}
    assert Measurement((0,), 'counts["0"] ** 2 / shots').evaluate(counts) == pytest.approx(2.25)
    assert Measurement((0,), '-(counts["0"] - counts["1"]) * 0.5 + +1').evaluate(counts) == pytest.approx(0.0)


def test_measurement_label_defaults_to_the_expression():
    assert Measurement((0,), '  counts["1"]  ').label == 'counts["1"]'
    assert Measurement((0,), 'counts["1"]', "ones").label == "ones"


def test_measurement_accepts_a_list_of_qubits():
    assert Measurement([1, 0], 'counts["10"]').qubits == (1, 0)  # type: ignore[arg-type]


def test_measurement_has_no_shortcuts():
    for name in ("population", "expectation", "cavity_population"):
        assert not hasattr(Measurement, name)


def test_an_expectation_result_reads_any_one_qubit_expression():
    expectation = np.array([0.0, 0.5, 1.0, -1.0])
    result = SimulationResult(
        times=np.linspace(0.0, 1.0, 4),
        observables=[expectation, np.zeros(4)],
        metadata={"observable_kind": "qubit_expectations", "num_qubits": 2},
    )
    population = ((1.0 - expectation) / 2.0).tolist()
    for expression in ('counts["1"] / shots', 'counts["1"]/shots', '1 - counts["0"] / shots'):
        applied = apply_measurements(result, [Measurement((0,), expression)])
        assert applied.observables[0].tolist() == pytest.approx(population)
        assert "observable_kind" not in applied.metadata
    pauli = apply_measurements(result, [Measurement((0,), '(counts["0"] - counts["1"]) / shots')])
    assert pauli.observables[0].tolist() == pytest.approx(expectation.tolist())
    with pytest.raises(ValueError, match="returns Pauli expectations, not shot counts"):
        apply_measurements(result, [Measurement((0, 1), '(counts["00"] - counts["11"]) / shots')])


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("0.0 ** -1", "divides by zero"),
        ("10.0 ** 400", "too large"),
        ("(-1) ** 0.5", "finite real"),
        ('1 / (counts["0"] - counts["0"])', "finite real"),
    ],
)
def test_an_expectation_result_rejects_a_bad_value(expression: str, message: str):
    result = SimulationResult(
        times=np.array([0.0]),
        observables=[np.array([0.0])],
        metadata={"observable_kind": "qubit_expectations"},
    )
    with pytest.raises(ValueError, match=message):
        apply_measurements(result, [Measurement((0,), expression, "curve")])


@pytest.mark.parametrize("qubits", [(), "01", 3, (0, 0), (-1,), (True,), (1.0,)])
def test_measurement_rejects_bad_qubits(qubits: object):
    with pytest.raises(ValueError, match="qubits"):
        Measurement(qubits, "shots")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("", "non-empty"),
        ("   ", "non-empty"),
        (7, "non-empty"),
        ("1" * 1001, "at most 1000"),
        ("counts[", "not valid"),
        ("__import__('os')", "cannot use"),
        ("shots.real", "cannot use"),
        ("total", "cannot use"),
        ("True", "cannot use"),
        ("1j", "cannot use"),
        ("'0'", "cannot use"),
        ("shots % 2", "cannot use"),
        ("not shots", "cannot use"),
        ("shots[0]", "cannot use"),
        ("counts[0]", "quoted bitstring"),
        ("counts[shots]", "quoted bitstring"),
        ('counts["0"]', "2 characters"),
        ('counts["0a"]', "2 characters"),
    ],
)
def test_measurement_rejects_disallowed_expressions(expression: object, message: str):
    with pytest.raises(ValueError, match=message):
        Measurement((0, 1), expression)  # type: ignore[arg-type]


def test_measurement_rejects_counts_that_are_too_short():
    with pytest.raises(ValueError, match="counts have 2 qubits, but this measurement reads qubit 2"):
        Measurement((2,), "shots").evaluate({"01": 1})


@pytest.mark.parametrize(
    ("expression", "counts", "message"),
    [
        ('counts["1"] / shots', {}, "divides by zero"),
        ("0.0 ** -1", {"0": 1}, "divides by zero"),
        ("10.0 ** 400", {"0": 1}, "too large"),
        ("1e308 * 10", {"0": 1}, "finite real"),
        ("(-1) ** 0.5", {"0": 1}, "finite real"),
    ],
)
def test_measurement_rejects_values_that_are_not_finite_reals(expression: str, counts: dict[str, int], message: str):
    with pytest.raises(ValueError, match=message):
        Measurement((0,), expression).evaluate(counts)


def test_apply_measurements_replaces_observables_with_one_curve_each():
    result = _result([{"000": 3, "110": 1}, {"110": 4}])
    applied = apply_measurements(
        result,
        [Measurement((0,), 'counts["1"] / shots', "P(1) on 0"), Measurement((0, 1), 'counts["11"]', "both")],
    )
    assert [curve.tolist() for curve in applied.observables] == [[0.25, 1.0], [1.0, 4.0]]
    assert applied.counts == result.counts
    assert applied.metadata["num_qubits"] == 3
    assert applied.metadata["measurements"] == [
        {"qubits": [0], "expression": 'counts["1"] / shots', "label": "P(1) on 0"},
        {"qubits": [0, 1], "expression": 'counts["11"]', "label": "both"},
    ]
    assert result.observables[0].tolist() == [0.0, 0.0]


def test_apply_measurements_requires_counts():
    with pytest.raises(ValueError, match="this result has no shot counts"):
        apply_measurements(_result(None), [Measurement((0,), 'counts["1"] / shots')])


def test_apply_measurements_names_an_expectation_backend():
    result = SimulationResult(
        times=np.array([0.0]),
        observables=[np.array([1.0])],
        metadata={"circuit_backend": "pauli_propagation"},
    )
    with pytest.raises(ValueError, match="the pauli_propagation backend has no shot counts"):
        apply_measurements(result, [Measurement((0,), 'counts["1"] / shots')])


def test_apply_measurements_requires_a_measurement():
    with pytest.raises(ValueError, match="at least one measurement"):
        apply_measurements(_result([{"0": 1}]), [])
