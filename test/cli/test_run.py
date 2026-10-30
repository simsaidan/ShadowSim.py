"""Tests for building a QuTiP simulator from a builder-page selection."""

import builtins
import importlib
import json
import math
import threading
import types
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from http.server import HTTPServer
from pathlib import Path
from typing import Literal, Protocol, Union

import numpy as np
import pytest

from shadowsim.backends import listed_backends
from shadowsim.cli.run import (
    _initial_state,
    _measured_result,
    _measurements,
    _observable_labels,
    _series_name,
    build_simulator,
    run_page,
)
from shadowsim.cli.serve import _Handler
from shadowsim.models import (
    ising,
    jaynes_cummings,
    jaynes_cummings_hubbard,
    tavis_cummings,
    tavis_cummings_hubbard,
)
from shadowsim.models.catalog import _describe_models, listed_model_terms, listed_models
from shadowsim.simulators.catalog import _describe_simulator, listed_simulators
from shadowsim.simulators.result import _resource_record


def _selection(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state": "basis",
        "model": "ising",
        "simulator": "qutip",
        "backend": "aer",
        "measure": "z",
        "then": "save",
        "qubits": "2",
        "total": "0.5",
        "basis": "10",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def forbid_qutip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if building a rejected selection imports QuTiP."""
    real_import = builtins.__import__

    def guarded(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        root = name.split(".", 1)[0]
        if root == "qutip" or name == "shadowsim.simulators.qutip_simulator":
            raise AssertionError(f"imported {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"backend": "qiskit"}, "only Aer"),
        ({"backend": "other"}, "only Aer"),
        ({"total": "0"}, "positive number"),
        ({"total": 0}, "positive number"),
        ({"total": "-1"}, "positive number"),
        ({"total": ""}, "positive number"),
        ({"qubits": "1"}, ">= 2"),
        ({"qubits": 1}, ">= 2"),
        ({"qubits": "2.5"}, "integer"),
        ({"qubits": 2.5}, "integer"),
        ({"qubits": float("nan")}, "integer"),
        ({"qubits": "nope"}, "integer"),
        ({"qubits": True}, "integer"),
        ({"qubits": None}, "integer"),
        ({"qubits": ""}, "integer"),
        ({"total": "nope"}, "positive number"),
        ({"total": True}, "positive number"),
        ({"total": float("inf")}, "positive number"),
        ({"simulator": None}, "unknown simulator"),
        ({"state": "nope"}, "unknown initial state"),
        ({"model": "nope"}, "unknown model"),
        ({"measure": "nope"}, "unknown measurement"),
    ],
)
def test_build_simulator_rejects(overrides: dict[str, object], message: str, forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match=message):
        build_simulator(_selection(**overrides))


def test_qutip_without_a_backend_reaches_the_simulator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shadowsim.cli.run._qutip_simulator", lambda *_args, **_kwargs: "built")
    selection = _selection()
    del selection["backend"]
    assert build_simulator(selection, time_steps=2) == "built"


def test_circuit_simulator_without_a_backend_is_rejected(forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match="only Aer"):
        build_simulator(_selection(simulator="trotterization", backend=None))


@pytest.mark.parametrize("time_steps", [0, True, 1.5])
def test_time_steps_must_be_a_positive_integer(time_steps: object, forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_simulator(_selection(), time_steps=time_steps)  # type: ignore[arg-type]


def test_missing_total_time_is_rejected(forbid_qutip: None) -> None:
    payload = _selection()
    del payload["total"]
    with pytest.raises(ValueError, match="positive number"):
        build_simulator(payload)


@pytest.mark.qutip
def test_build_simulator_runs_a_small_ising() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(), time_steps=3)
    assert simulator.num_qubits == 2
    assert simulator.total_time == 0.5
    assert simulator.time_steps == 3
    assert simulator.initial_state.get_num_qubits() == 2
    result = simulator.simulate()
    assert len(result.times) == 3
    assert len(result.observables) == 2
    assert all(len(curve) == 3 for curve in result.observables)


@pytest.mark.qutip
@pytest.mark.parametrize("state", ["basis", "gray", "angle", "amplitude"])
def test_initial_state_uses_the_model_qubit_count(state: str) -> None:
    pytest.importorskip("qutip")
    overrides: dict[str, object] = {"state": state, "qubits": "3"}
    if state == "basis":
        overrides["basis"] = "100"
    elif state == "gray":
        overrides["gray"] = "100"
    elif state == "angle":
        overrides["angles"] = [0.0, 0.0, 0.0]
    elif state == "amplitude":
        overrides["amplitudes"] = [1.0, 0.0, 0.0, 0.0, 0.0]
    simulator = build_simulator(_selection(**overrides), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
@pytest.mark.parametrize("model_id", ["tavis_cummings", "tavis_cummings_hubbard"])
def test_tavis_cummings_ignores_the_qubits_field(model_id: str) -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(model=model_id, qubits="1", basis="100"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
def test_jaynes_cummings_ignores_the_qubits_field() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(model="jaynes_cummings", qubits="1", basis="100"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


def _built_model(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> object:
    """Return the model ``build_simulator`` would hand to QuTiP."""
    monkeypatch.setattr("shadowsim.cli.run._qutip_simulator", lambda model, *_args, **_kwargs: model)
    return build_simulator(_selection(**overrides), time_steps=2)


def _same_operators(got: object, expected: object) -> None:
    """Require two models to carry the same full-space operators."""
    for name in ("full_hamiltonians", "c_ops_full"):
        left = getattr(got, name)
        right = getattr(expected, name)
        assert len(left) == len(right)
        for item, reference in zip(left, right, strict=True):
            assert np.allclose(item.matrix, reference.matrix)


def test_factory_arguments_build_the_ising_model(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _built_model(
        monkeypatch,
        qubits="4",
        basis="0000",
        factory={
            "J": "0.5",
            "h": "0.25",
            "field": "classical",
            "boundary": "open",
            "edges": "0-1, 2-3",
        },
    )
    assert model.J == 0.5
    assert model.h == 0.25
    assert model.field == "classical"
    assert model.edges == [(0, 1), (2, 3)]
    assert model.topology == "custom"


def test_factory_arguments_build_jaynes_cummings(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _built_model(
        monkeypatch,
        model="jaynes_cummings",
        basis="100",
        factory={"omega_c": "10", "g": "4"},
    )
    _same_operators(model, jaynes_cummings(omega_c=10, g=4))


@pytest.mark.parametrize(
    ("model_id", "reference"),
    [
        ("jaynes_cummings_hubbard", jaynes_cummings_hubbard(n_cavities=2, nu=1.5, omega_c=10, g=4)),
        (
            "tavis_cummings_hubbard",
            tavis_cummings_hubbard(n_cavities=2, n_emitters=1, nu=1.5, omega_c=10, g=4),
        ),
    ],
)
def test_factory_arguments_build_a_hubbard_model(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    reference: object,
) -> None:
    model = _built_model(
        monkeypatch,
        model=model_id,
        cavities=2,
        nu=1.5,
        basis="000000",
        factory={"omega_c": "10", "g": "4"},
    )
    _same_operators(model, reference)


def test_factory_arguments_accept_a_per_emitter_list(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _built_model(
        monkeypatch,
        model="tavis_cummings",
        emitters=2,
        basis="0000",
        factory={"omega_c": "10", "g": "4, 5"},
    )
    _same_operators(model, tavis_cummings(n_emitters=2, omega_c=10, g=[4, 5]))


def test_factory_arguments_accept_numbers_lists_and_parenthesized_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _built_model(
        monkeypatch,
        qubits="4",
        basis="0000",
        factory={"J": 0.5, "h": 1, "field": " classical ", "edges": "(0, 1), (2, 3)"},
    )
    assert model.J == 0.5
    assert model.h == 1.0
    assert model.field == "classical"
    assert model.edges == [(0, 1), (2, 3)]

    listed = _built_model(monkeypatch, qubits="3", basis="000", factory={"edges": [[0, 1], (1, 2)], "J": 1})
    assert listed.edges == [(0, 1), (1, 2)]

    blank = _built_model(monkeypatch, factory={"edges": "  "})
    assert blank.edges == ising(n_qubits=2).edges

    cavity = _built_model(
        monkeypatch,
        model="tavis_cummings",
        emitters=2,
        basis="0000",
        factory={"g": [4, 5]},
    )
    _same_operators(cavity, tavis_cummings(n_emitters=2, g=[4, 5]))


def test_missing_factory_keeps_the_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    ising_model = _built_model(monkeypatch)
    reference = ising(n_qubits=2)
    assert ising_model.J == reference.J
    assert ising_model.h == reference.h
    assert ising_model.field == reference.field
    assert ising_model.edges == reference.edges

    cavity = _built_model(monkeypatch, model="jaynes_cummings", basis="100")
    _same_operators(cavity, jaynes_cummings())
    emitters = _built_model(monkeypatch, model="tavis_cummings", emitters=2, basis="0000")
    _same_operators(emitters, tavis_cummings(n_emitters=2))


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"factory": {"J": "0", "h": "0"}}, "cannot both be zero"),
        ({"factory": {"J": "inf"}}, "real number"),
        ({"factory": {"J": True}}, "real number"),
        ({"factory": {"J": float("nan")}}, "real number"),
        ({"factory": {"J": {"bad": 1}}}, "real number"),
        ({"factory": {"field": "nope"}}, "one of"),
        ({"factory": {"edges": 3}}, "pairs"),
        ({"factory": {"edges": [[0]]}}, "pairs"),
        ({"factory": {"edges": [0]}}, "pairs"),
        ({"factory": {"edges": [[True, 1]]}}, "pairs"),
        ({"factory": {"edges": "(0, 1) junk"}}, "pairs"),
        ({"factory": {"edges": ",,,"}}, "pairs"),
        ({"model": "jaynes_cummings", "factory": {"g": "1, 2"}}, "real number"),
        ({"model": "tavis_cummings", "emitters": 2, "factory": {"g": "4, "}}, "real number"),
        ({"factory": {"edges": "nope"}}, "pairs"),
        ({"factory": {"boundary": "periodic", "edges": "0-1"}}, "cannot be combined"),
        ({"factory": {"boundary": "periodic"}}, "n_qubits >= 3"),
        ({"factory": []}, "factory arguments must be an object"),
        (
            {"model": "tavis_cummings", "emitters": 2, "factory": {"g": "1, 2, 3"}},
            "sequence of length 2",
        ),
    ],
)
def test_factory_arguments_are_rejected_before_import(
    forbid_qutip: None,
    overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_simulator(_selection(**overrides))


@pytest.mark.qutip
@pytest.mark.parametrize("model_id", ["tavis_cummings", "tavis_cummings_hubbard"])
def test_tavis_cummings_sizes_from_the_emitter_count(model_id: str) -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(
        _selection(model=model_id, emitters=2, qubits="4", basis="0000"),
        time_steps=2,
    )
    assert simulator.num_qubits == 4
    assert simulator.initial_state.get_num_qubits() == 4


@pytest.mark.qutip
def test_tavis_cummings_hubbard_sizes_from_cavities_and_hopping() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(
        _selection(model="tavis_cummings_hubbard", cavities=2, emitters=1, nu=1.5, basis="000000"),
        time_steps=2,
    )
    assert simulator.num_qubits == 6
    assert len(simulator.hamiltonians) == 7


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"cavities": 0}, "cavities must be an integer of at least 1"),
        ({"cavities": True}, "cavities must be an integer of at least 1"),
        ({"nu": "nope"}, "hopping must be a real number"),
        ({"nu": True}, "hopping must be a real number"),
        ({"nu": []}, "hopping must be a real number"),
        ({"nu": "  "}, "hopping must be a real number"),
        ({"nu": float("inf")}, "hopping must be a real number"),
        ({"cavities": 2, "emitters": 6}, "at most 15 qubits"),
    ],
)
def test_tavis_cummings_hubbard_page_limits(forbid_qutip: None, overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build_simulator(_selection(model="tavis_cummings_hubbard", basis="100", **overrides))


@pytest.mark.qutip
def test_jaynes_cummings_hubbard_sizes_from_cavities_and_hopping() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(
        _selection(model="jaynes_cummings_hubbard", cavities=2, emitters=5, nu=1.5, basis="000000"),
        time_steps=2,
    )
    assert simulator.num_qubits == 6
    assert len(simulator.hamiltonians) == 7


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"cavities": 0}, "cavities must be an integer of at least 1"),
        ({"cavities": True}, "cavities must be an integer of at least 1"),
        ({"nu": "nope"}, "hopping must be a real number"),
        ({"nu": True}, "hopping must be a real number"),
        ({"nu": []}, "hopping must be a real number"),
        ({"nu": "  "}, "hopping must be a real number"),
        ({"nu": float("inf")}, "hopping must be a real number"),
        ({"cavities": 6}, "at most 15 qubits"),
    ],
)
def test_jaynes_cummings_hubbard_page_limits(forbid_qutip: None, overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build_simulator(_selection(model="jaynes_cummings_hubbard", basis="100", **overrides))


@pytest.mark.parametrize("model_id", ["tavis_cummings", "tavis_cummings_hubbard"])
@pytest.mark.parametrize("emitters", [0, 14, True, "nope"])
def test_tavis_emitter_count_is_rejected_before_import(forbid_qutip: None, model_id: str, emitters: object) -> None:
    with pytest.raises(ValueError, match="emitters must be an integer from 1 to 13"):
        build_simulator(_selection(model=model_id, emitters=emitters, basis="100"))


@pytest.mark.parametrize("model_id", ["tavis_cummings", "tavis_cummings_hubbard"])
def test_tavis_emitter_count_must_match_the_state(forbid_qutip: None, model_id: str) -> None:
    with pytest.raises(ValueError, match=r"qubit count \(4\)"):
        build_simulator(_selection(model=model_id, emitters=2, basis="000"))


def test_basis_bit_string_selects_that_state() -> None:
    state = _initial_state("basis", 2, "01")
    vector = state.to_numpy().reshape(-1)
    assert vector.shape == (4,)
    assert vector[1] == 1
    assert _initial_state("basis", 15, "1" * 15).get_num_qubits() == 15


@pytest.mark.parametrize(
    ("basis", "qubits", "match"),
    [
        (None, 2, "0 and 1"),
        ("", 2, "0 and 1"),
        ("2", 2, "0 and 1"),
        ("10 ", 2, "0 and 1"),
        ("1" * 16, 16, "15"),
        ("101", 2, "qubit count"),
    ],
)
def test_basis_bit_string_rejects_bad_input(basis: object, qubits: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _initial_state("basis", qubits, basis)


def test_gray_bit_string_prepares_the_gray_state() -> None:
    vector = _initial_state("gray", 3, "101").to_numpy().reshape(-1)
    assert vector.shape == (8,)
    assert vector[7] == 1


def test_gray_bit_string_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="0 and 1"):
        _initial_state("gray", 3, "102")
    with pytest.raises(ValueError, match="qubit count"):
        _initial_state("gray", 2, "101")


def test_angle_list_prepares_one_rotation_per_qubit() -> None:
    vector = _initial_state("angle", 1, [math.pi / 2]).to_numpy().reshape(-1)
    assert vector[0] == pytest.approx(math.cos(math.pi / 4))
    assert vector[1] == pytest.approx(math.sin(math.pi / 4))


def test_angle_list_rejects_the_wrong_length() -> None:
    with pytest.raises(ValueError, match="angles must be 2"):
        _initial_state("angle", 2, [0.0])


def test_amplitude_list_pads_to_the_model_qubit_count() -> None:
    state = _initial_state("amplitude", 2, [1.0, 0.5, 0.25])
    assert state.get_num_qubits() == 2
    with pytest.raises(ValueError, match="prepares 1 qubit"):
        _initial_state("amplitude", 2, [1.0])
    with pytest.raises(ValueError, match="non-zero"):
        _initial_state("amplitude", 1, [0.0])


def test_initial_state_rejects_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown initial state"):
        _initial_state("nope", 2)


@pytest.mark.qutip
def test_pauli_measurement_records_one_curve_per_qubit() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(measure="x"), time_steps=2)
    assert len(simulator.observables) == 2


def test_measure_sites_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError, match="measured qubits"):
        build_simulator(_selection(sites=[]), time_steps=2)


def test_measure_sites_rejects_an_index_past_the_model() -> None:
    with pytest.raises(ValueError, match="indexes from 0 to 1"):
        build_simulator(_selection(sites=[2]), time_steps=2)


@pytest.mark.qutip
def test_pauli_subset_records_the_selected_qubit() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(sites=[1]), time_steps=2)
    assert len(simulator.observables) == 1
    assert simulator.observables[0].name == "IZ"


@pytest.mark.qutip
def test_integral_float_settings_build_the_simulator() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(qubits=2.0, total=0.5), time_steps=2)
    assert simulator.num_qubits == 2
    assert simulator.total_time == 0.5


@pytest.mark.qutip
def test_then_does_not_change_the_simulator() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(then="plot"), time_steps=2)
    assert simulator.id == "qutip_simulator"
    assert simulator.num_qubits == 2


def test_paths_inside_the_output_directory_are_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "results"
    with pytest.raises(ValueError, match="unknown simulator"):
        run_page(_selection(simulator="nope", then="save", save_path="results/run1"), output_root=root)
    with pytest.raises(ValueError, match="unknown simulator"):
        run_page(_selection(simulator="nope", then="save", save_path=str(root / "nested")), output_root=root)
    with pytest.raises(ValueError, match="unknown simulator"):
        run_page(_selection(simulator="nope", then="export", export_path="results"), output_root=root)
    with pytest.raises(ValueError, match="unknown simulator"):
        run_page(
            _selection(simulator="nope", then="export", export_path=str(root / "metrics.json")),
            output_root=root,
        )


def test_paths_outside_the_output_directory_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = (tmp_path / "results").resolve()
    outside = tmp_path.parent / "outside"
    with pytest.raises(ValueError, match="save path must stay under"):
        run_page(_selection(then="save", save_path="results/../../outside"), output_root=root)
    with pytest.raises(ValueError, match="save path must stay under"):
        run_page(_selection(then="save", save_path=str(outside)), output_root=root)
    with pytest.raises(ValueError, match="export path must stay under"):
        run_page(_selection(then="export", export_path="results/../../outside"), output_root=root)
    with pytest.raises(ValueError, match="export path must stay under"):
        run_page(_selection(then="export", export_path=str(outside / "metrics.json")), output_root=root)


def test_a_symlink_that_leaves_the_output_directory_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "results"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "metrics.json").symlink_to(outside / "metrics.json")
    resolved = root.resolve()
    with pytest.raises(ValueError, match="save path must stay under"):
        run_page(_selection(then="save", save_path="results/link"), output_root=resolved)
    with pytest.raises(ValueError, match="export path must stay under"):
        run_page(_selection(then="export", export_path="results/metrics.json"), output_root=resolved)


def test_save_rejects_an_empty_path() -> None:
    with pytest.raises(ValueError, match="save path"):
        run_page(_selection(then="save", save_path="  "))


@pytest.mark.qutip
def test_save_writes_the_result(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "custom"
    payload = run_page(_selection(then="save", save_path=str(destination), time_steps=2))
    assert payload["saved"] == [str(destination)]
    assert (destination / "times.npy").is_file()
    assert (destination / "observables.npz").is_file()
    assert (destination / "meta.json").is_file()


@pytest.mark.qutip
def test_save_uses_the_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qutip")
    monkeypatch.chdir(tmp_path)
    payload = run_page(_selection(then="save", time_steps=2))
    assert payload["saved"] == [str(Path("results") / "run1")]
    assert (tmp_path / "results" / "run1" / "meta.json").is_file()


@pytest.mark.qutip
def test_save_writes_each_benchmark_result(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "bench"
    payload = run_page(
        _selection(
            then="save",
            save_path=str(destination),
            simulators=[
                {"simulator": "qutip", "time_steps": 2},
                {"simulator": "qutip", "time_steps": 2},
            ],
        )
    )
    assert payload["saved"] == [str(destination / "sim_1"), str(destination / "sim_2")]
    assert (destination / "sim_1" / "meta.json").is_file()
    assert (destination / "sim_2" / "meta.json").is_file()


def test_export_rejects_an_empty_path() -> None:
    with pytest.raises(ValueError, match="export path"):
        run_page(_selection(then="export", export_path="  "))


@pytest.mark.qutip
def test_export_writes_resource_metrics(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "metrics"
    payload = run_page(_selection(then="export", export_path=str(destination), time_steps=2))
    written = list(destination.glob("resource_metrics_*.json"))
    assert len(written) == 1
    assert payload["exported"] == str(written[0])
    assert "saved" not in payload
    body = json.loads(written[0].read_text())
    assert "errors" not in body
    record = body["resources"][0]
    assert record["simulator_id"] == "qutip_simulator"
    assert isinstance(record["wall_time_s"], float)
    assert record["shots_per_job"] is None
    assert record["num_jobs"] is None
    assert record["total_shots"] is None
    assert record["depth"] == "N/A"
    assert record["width"] == "N/A"
    assert record["gate_count"] == "N/A"
    assert record["t_count"] == "N/A"
    assert record["toffoli_count"] == "N/A"


@pytest.mark.qutip
def test_export_writes_a_json_file(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "metrics.json"
    payload = run_page(_selection(then="export", export_path=str(destination), time_steps=2))
    assert payload["exported"] == str(destination)
    assert json.loads(destination.read_text())["resources"][0]["simulator_id"] == "qutip_simulator"


@pytest.mark.qutip
def test_export_uses_the_results_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qutip")
    monkeypatch.chdir(tmp_path)
    payload = run_page(_selection(then="export", time_steps=2))
    written = list((tmp_path / "results").glob("resource_metrics_*.json"))
    assert len(written) == 1
    assert payload["exported"] == str(written[0].relative_to(tmp_path))


@pytest.mark.qutip
def test_none_paths_use_the_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qutip")
    monkeypatch.chdir(tmp_path)
    payload = run_page(_selection(thens=["save", "export"], save_path=None, export_path=None, time_steps=2))
    assert payload["saved"] == [str(Path("results") / "run1")]
    written = list((tmp_path / "results").glob("resource_metrics_*.json"))
    assert payload["exported"] == str(written[0].relative_to(tmp_path))


@pytest.mark.qutip
def test_export_writes_benchmark_metrics(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "bench-metrics"
    payload = run_page(
        _selection(
            then="export",
            export_path=str(destination),
            simulators=[
                {"simulator": "qutip", "time_steps": 2},
                {"simulator": "qutip", "time_steps": 2},
            ],
        )
    )
    written = list(destination.glob("benchmark_error_metrics_*.json"))
    assert len(written) == 1
    assert payload["exported"] == str(written[0])
    body = json.loads(written[0].read_text())
    assert body["errors"]
    assert len(body["resources"]) == 2


@pytest.mark.qutip
def test_export_writes_benchmark_metrics_to_a_json_file(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "bench.json"
    payload = run_page(
        _selection(
            then="export",
            export_path=str(destination),
            simulators=[
                {"simulator": "qutip", "time_steps": 2},
                {"simulator": "qutip", "time_steps": 2},
            ],
        )
    )
    assert payload["exported"] == str(destination)
    assert json.loads(destination.read_text())["errors"]


@pytest.mark.qutip
def test_benchmark_requires_a_recorded_result(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qutip")
    monkeypatch.setattr("shadowsim.cli.run.Benchmark.run", lambda self: None)
    with pytest.raises(ValueError, match="Results are not available"):
        run_page(
            _selection(
                simulators=[
                    {"simulator": "qutip", "time_steps": 2},
                    {"simulator": "qutip", "time_steps": 2},
                ]
            )
        )


@pytest.mark.qutip
def test_duplicate_measure_sites_are_kept_once() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(sites=[0, 0]), time_steps=2)
    assert len(simulator.observables) == 1


@pytest.mark.qiskit
def test_export_counts_shots_for_a_circuit_simulator(tmp_path: Path) -> None:
    pytest.importorskip("qiskit_aer")
    destination = tmp_path / "metrics.json"
    payload = run_page(
        _selection(
            simulator="trotterization",
            then="export",
            export_path=str(destination),
            time_steps=2,
            num_steps=1,
            shots=4,
        )
    )
    record = json.loads(destination.read_text())["resources"][0]
    assert record["shots_per_job"] == 4
    assert record["num_jobs"] == 2
    assert record["total_shots"] == 8
    assert record["width"] == 2
    assert isinstance(record["depth"], int)
    assert isinstance(record["gate_count"], int)
    assert record["depth"] > 0
    assert record["gate_count"] > 0
    assert record["t_count"] == 0
    assert record["toffoli_count"] == 0
    assert payload["resources"] == [record]
    assert payload["labels"] == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]


def test_thens_overrides_a_single_then() -> None:
    with pytest.raises(ValueError, match="export path"):
        run_page(_selection(then="save", thens=["export"], export_path="  "))


@pytest.mark.qutip
def test_save_and_export_run_together(tmp_path: Path) -> None:
    pytest.importorskip("qutip")
    destination = tmp_path / "both"
    metrics = tmp_path / "metrics.json"
    payload = run_page(
        _selection(
            thens=["plot", "save", "export"],
            save_path=str(destination),
            export_path=str(metrics),
            time_steps=2,
        )
    )
    assert payload["saved"] == [str(destination)]
    assert payload["exported"] == str(metrics)
    assert (destination / "meta.json").is_file()
    body = json.loads(metrics.read_text())
    assert body["resources"][0]["simulator_id"] == "qutip_simulator"
    assert "times" in payload


def _request(method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    finally:
        thread.join(timeout=60)
        server.server_close()


def _post(body: bytes, *, path: str = "/runs") -> tuple[int, bytes]:
    return _request("POST", path, body)


def test_post_runs_rejects_a_selection() -> None:
    status, body = _post(json.dumps(_selection(simulator="nope")).encode())
    payload = json.loads(body)
    assert status == 400
    assert "unknown simulator" in payload["error"]


@pytest.mark.qiskit
def test_pauli_propagation_builds_a_trotter_run() -> None:
    pytest.importorskip("qiskit")
    simulator = build_simulator(
        _selection(
            simulator="trotterization",
            backend="paulipropagation",
            time_steps=2,
            num_steps=1,
            shots=0,
        )
    )
    assert simulator.circuit_backend.name == "pauli_propagation"
    assert simulator.circuit_backend.max_weight == math.inf
    assert simulator.circuit_backend.min_abs_coeff == 1e-10
    assert not hasattr(simulator.circuit_backend, "shots")
    record = _resource_record(simulator, 0.2)
    assert record["depth"] == "N/A"
    assert record["width"] == "N/A"
    assert record["gate_count"] == "N/A"
    assert record["t_count"] == "N/A"
    assert record["toffoli_count"] == "N/A"


@pytest.mark.qiskit
def test_pauli_propagation_uses_posted_truncation() -> None:
    pytest.importorskip("qiskit")
    simulator = build_simulator(
        _selection(
            simulator="trotterization",
            backend="paulipropagation",
            time_steps=2,
            num_steps=1,
            max_weight="4",
            min_abs_coeff="1e-8",
        )
    )
    assert simulator.circuit_backend.max_weight == 4
    assert simulator.circuit_backend.min_abs_coeff == 1e-8
    with pytest.raises(ValueError, match="max weight"):
        build_simulator(
            _selection(
                simulator="trotterization",
                backend="paulipropagation",
                time_steps=2,
                max_weight="-1",
            )
        )


@pytest.mark.qiskit
def test_pauli_propagation_checks_every_posted_truncation() -> None:
    pytest.importorskip("qiskit")
    posted = dict(simulator="trotterization", backend="paulipropagation", time_steps=2, num_steps=1)
    simulator = build_simulator(_selection(**posted, max_weight=4, min_abs_coeff=1e-8))
    assert simulator.circuit_backend.max_weight == 4
    assert simulator.circuit_backend.min_abs_coeff == 1e-8
    unlimited = build_simulator(_selection(**posted, max_weight=" infinity ", min_abs_coeff="0"))
    assert unlimited.circuit_backend.max_weight == math.inf
    assert unlimited.circuit_backend.min_abs_coeff == 0.0
    for overrides, message in (
        ({"max_weight": ""}, "max weight"),
        ({"max_weight": "nope"}, "max weight"),
        ({"min_abs_coeff": "inf"}, "min coefficient"),
        ({"min_abs_coeff": "nan"}, "min coefficient"),
    ):
        with pytest.raises(ValueError, match=message):
            build_simulator(_selection(**posted, **overrides))
    for overrides, message in (
        ({"max_weight": True}, "max weight"),
        ({"min_abs_coeff": None}, "min coefficient"),
    ):
        with pytest.raises(TypeError, match=message):
            build_simulator(_selection(**posted, **overrides))


@pytest.mark.qiskit
def test_pauli_propagation_rejects_split_j() -> None:
    pytest.importorskip("qiskit")
    with pytest.raises(ValueError, match="shot budget"):
        build_simulator(_selection(simulator="splitjmatrix", backend="paulipropagation", time_steps=2))


@pytest.mark.qiskit
def test_aer_uses_posted_basis_gates() -> None:
    pytest.importorskip("qiskit_aer")
    posted = {"simulator": "trotterization", "time_steps": 2, "num_steps": 1}
    assert build_simulator(_selection(**posted)).circuit_backend.basis_gates is None
    assert build_simulator(_selection(**posted, basis_gates="  ")).circuit_backend.basis_gates is None
    named = build_simulator(_selection(**posted, basis_gates="RX, ry, rx, cx"))
    assert named.circuit_backend.basis_gates == ("rx", "ry", "cx")
    listed = build_simulator(_selection(**posted, basis_gates=["u", "cx"]))
    assert listed.circuit_backend.basis_gates == ("u", "cx")
    with pytest.raises(ValueError, match=r"^Unknown gate foo\.$"):
        build_simulator(_selection(**posted, basis_gates="foo"))
    with pytest.raises(ValueError, match=r"^Enter at least one gate\.$"):
        build_simulator(_selection(**posted, basis_gates=",,,"))
    with pytest.raises(ValueError, match="sequence of gate names"):
        build_simulator(_selection(**posted, basis_gates=1))
    with pytest.raises(ValueError, match="sequence of gate names"):
        build_simulator(_selection(**posted, basis_gates=["cx", 1]))


@pytest.mark.qiskit
def test_aer_posted_basis_that_cannot_compile_is_a_value_error() -> None:
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")
    from qiskit import QuantumCircuit

    simulator = build_simulator(
        _selection(simulator="trotterization", time_steps=2, num_steps=1, basis_gates="x, y, z")
    )
    circuit = QuantumCircuit(1)
    circuit.t(0)
    with pytest.raises(ValueError, match=r"^Cannot compile t into x, y, and z\.$"):
        simulator.circuit_backend.t_count(circuit)


@pytest.mark.qiskit
def test_pauli_propagation_ignores_basis_gates() -> None:
    pytest.importorskip("qiskit")
    simulator = build_simulator(
        _selection(
            simulator="trotterization",
            backend="paulipropagation",
            time_steps=2,
            num_steps=1,
            basis_gates="foo",
        )
    )
    assert simulator.circuit_backend.name == "pauli_propagation"


@pytest.mark.qiskit
@pytest.mark.parametrize("simulator_id", ["trotterization", "splitjmatrix"])
def test_circuit_simulator_runs_ising_on_aer(simulator_id: str) -> None:
    pytest.importorskip("qiskit_aer")
    simulator = build_simulator(_selection(simulator=simulator_id))
    assert simulator.time_steps == 11
    assert simulator.num_steps == 4
    assert simulator.circuit_backend.shots == 256
    assert simulator.seed == 0
    simulator.simulate()
    result = _measured_result(simulator, _selection(simulator=simulator_id))
    assert len(result.times) == 11
    assert len(result.observables) == 2
    assert all(len(curve) == 11 for curve in result.observables)


def test_trotterization_rejects_an_open_model() -> None:
    with pytest.raises(ValueError, match="closed-system"):
        build_simulator(_selection(simulator="trotterization", model="tavis_cummings", basis="100"))


def test_shot_parameters_are_validated() -> None:
    with pytest.raises(ValueError, match="shots"):
        build_simulator(_selection(simulator="splitjmatrix", shots=0))
    with pytest.raises(ValueError, match="order must be 1 or 2"):
        build_simulator(_selection(simulator="trotterization", order=3))
    with pytest.raises(ValueError, match="seed must be an integer"):
        build_simulator(_selection(simulator="trotterization", seed="nope"))


@pytest.mark.qutip
def test_qutip_time_steps_come_from_the_selection() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(time_steps="4"), time_steps=2)
    assert simulator.time_steps == 4


@pytest.mark.qiskit
def test_circuit_simulator_records_counts_and_measures_the_selected_qubit() -> None:
    pytest.importorskip("qiskit_aer")
    selection = _selection(simulator="trotterization", sites=[0], time_steps=2)
    simulator = build_simulator(selection)
    assert simulator.basis == "Z" * simulator.num_qubits
    assert simulator.simulate().observables == []
    result = _measured_result(simulator, selection)
    assert result.metadata["measurements"] == [
        {"qubits": [0], "expression": '(counts["0"] - counts["1"]) / shots', "label": "expectation on 0"}
    ]


@pytest.mark.qiskit
def test_split_j_reads_system_qubits_without_an_ancilla_offset() -> None:
    pytest.importorskip("qiskit_aer")
    selection = _selection(simulator="splitjmatrix", sites=[0, 1], time_steps=1)
    simulator = build_simulator(selection)
    simulator.simulate()
    result = _measured_result(simulator, selection)
    assert [item["qubits"] for item in result.metadata["measurements"]] == [[0], [1]]
    np.testing.assert_allclose(np.array(result.observables), [[-1.0], [1.0]])


@pytest.mark.qiskit
def test_counts_measurement_evaluates_the_expression_on_aer() -> None:
    pytest.importorskip("qiskit_aer")
    selection = _selection(
        simulator="trotterization",
        measure="counts",
        sites=[1, 0],
        expression='counts["01"] / shots',
        time_steps=1,
    )
    simulator = build_simulator(selection)
    simulator.simulate()
    result = _measured_result(simulator, selection)
    assert result.metadata["measurements"] == [
        {"qubits": [1, 0], "expression": 'counts["01"] / shots', "label": 'counts["01"] / shots'}
    ]
    np.testing.assert_allclose(result.observables[0], [1.0])


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"simulator": "qutip"}, "QuTiP returns Pauli expectations"),
        ({"simulator": "trotterization", "backend": "paulipropagation"}, "PauliPropagation returns Pauli"),
    ],
)
def test_counts_measurement_needs_aer(extra: dict[str, object], message: str) -> None:
    selection = _selection(measure="counts", sites=[0], expression='counts["1"] / shots', **extra)
    with pytest.raises(ValueError, match=message):
        build_simulator(selection)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        (None, "needs an expression"),
        ('counts["11"] / shots', "1 characters"),
        ("__import__('os')", "cannot use"),
    ],
)
def test_counts_measurement_rejects_a_bad_expression(expression: object, message: str) -> None:
    selection = _selection(measure="counts", simulator="trotterization", sites=[0], expression=expression)
    with pytest.raises(ValueError, match=message):
        build_simulator(selection)


@pytest.mark.qutip
def test_qutip_result_is_already_measured() -> None:
    pytest.importorskip("qutip")
    selection = _selection(time_steps=2)
    simulator = build_simulator(selection)
    with pytest.raises(ValueError, match="Results are not available"):
        _measured_result(simulator, selection)
    simulated = simulator.simulate()
    assert _measured_result(simulator, selection) is simulated


@pytest.mark.qiskit
@pytest.mark.parametrize("simulator_id", ["trotterization", "splitjmatrix"])
def test_circuit_parameters_come_from_the_selection(simulator_id: str) -> None:
    pytest.importorskip("qiskit_aer")
    simulator = build_simulator(
        _selection(
            simulator=simulator_id,
            time_steps=2,
            num_steps=2,
            trotter_depth=2,
            shots=32,
            seed=-3,
            order=2,
        )
    )
    assert simulator.time_steps == 2
    assert simulator.num_steps == 2
    assert simulator.trotter_depth == 2
    assert simulator.circuit_backend.shots == 32
    assert simulator.seed == -3
    assert simulator.order == 2


def test_series_name_drops_the_simulator_suffix() -> None:
    assert _series_name("qutip_simulator") == "qutip"
    assert _series_name("split_jmatrix_simulator#2") == "split_jmatrix#2"


def test_observable_labels_name_each_measured_qubit() -> None:
    assert _observable_labels({"measure": "z", "sites": [0, 1]}, 2) == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    assert _observable_labels({"measure": "x", "sites": [1]}, 2) == ["⟨X⟩ on 1"]
    counts = {"measure": "counts", "sites": [0, 1], "expression": ' counts["01"] / shots '}
    assert _observable_labels(counts, 2) == ['counts["01"] / shots']
    with pytest.raises(ValueError, match="unknown measurement"):
        _observable_labels({"measure": "y", "sites": [0]}, 1)
    with pytest.raises(ValueError, match="unknown measurement"):
        _measurements({"measure": "y", "sites": [0]}, 1)


@pytest.mark.qutip
def test_run_payload_names_the_selected_qubits() -> None:
    pytest.importorskip("qutip")
    payload = run_page(_selection(measure="x", sites=[1], time_steps=2, then="plot"))
    assert payload["labels"] == ["⟨X⟩ on 1"]
    observables = payload["observables"]
    assert isinstance(observables, list)
    assert len(observables) == 1
    resources = payload["resources"]
    assert isinstance(resources, list)
    assert resources[0]["simulator_id"] == "qutip_simulator"
    assert resources[0]["wall_time_s"] == payload["runtime"]
    assert resources[0]["shots_per_job"] is None


@pytest.mark.qutip
def test_two_simulators_form_a_benchmark() -> None:
    pytest.importorskip("qutip")
    payload = run_page(
        _selection(
            simulators=[
                {"simulator": "qutip", "time_steps": 3},
                {"simulator": "qutip", "time_steps": 3},
            ]
        )
    )
    assert payload["algorithm"] == "benchmark"
    series = payload["series"]
    assert isinstance(series, list)
    assert [item["name"] for item in series] == ["qutip#1", "qutip#2"]
    assert [item["labels"] for item in series] == [
        ["qutip#1 · ⟨Z⟩ on 0", "qutip#1 · ⟨Z⟩ on 1"],
        ["qutip#2 · ⟨Z⟩ on 0", "qutip#2 · ⟨Z⟩ on 1"],
    ]
    assert payload["labels"] == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    resources = payload["resources"]
    assert isinstance(resources, list)
    assert [item["simulator_id"] for item in resources] == ["qutip_simulator#1", "qutip_simulator#2"]
    assert payload["runtime"] == pytest.approx(sum(item["wall_time_s"] for item in resources))
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert errors[0]["challenger_id"] == "qutip_simulator#2"
    assert errors[0]["observables"][0]["linf"] == pytest.approx(0)


@pytest.mark.qiskit
@pytest.mark.pauli_propagation
def test_benchmark_runs_trotter_on_aer_and_pauli_propagation() -> None:
    pytest.importorskip("qiskit_aer")
    from backends.test_pauli_propagation import _pauli_propagation_skip_reason

    reason = _pauli_propagation_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    payload = run_page(
        _selection(
            then="plot",
            simulator="trotterization",
            time_steps=2,
            num_steps=1,
            simulators=[
                {"simulator": "trotterization", "backend": "aer", "shots": 4},
                {"simulator": "trotterization", "backend": "paulipropagation"},
            ],
        )
    )
    assert payload["algorithm"] == "benchmark"
    series = payload["series"]
    assert isinstance(series, list)
    assert [item["name"] for item in series] == ["trotterization#1", "trotterization#2"]
    for item in series:
        observables = item["observables"]
        assert isinstance(observables, list)
        assert len(observables) == 2
        assert all(len(curve) == 2 for curve in observables)
    resources = payload["resources"]
    assert isinstance(resources, list)
    assert [item["simulator_id"] for item in resources] == [
        "trotterization_simulator#1",
        "trotterization_simulator#2",
    ]
    assert resources[0]["shots_per_job"] == 4
    assert resources[0]["num_jobs"] == 2
    assert resources[0]["total_shots"] == 8
    assert resources[1]["shots_per_job"] is None
    assert resources[1]["num_jobs"] is None
    assert resources[1]["total_shots"] is None
    assert isinstance(resources[0]["depth"], int)
    assert resources[0]["width"] == 2
    assert isinstance(resources[0]["gate_count"], int)
    assert resources[0]["t_count"] == 0
    assert resources[0]["toffoli_count"] == 0
    assert resources[1]["depth"] == "N/A"
    assert resources[1]["width"] == "N/A"
    assert resources[1]["gate_count"] == "N/A"
    assert resources[1]["t_count"] == "N/A"
    assert resources[1]["toffoli_count"] == "N/A"
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert errors[0]["challenger_id"] == "trotterization_simulator#2"


@pytest.mark.qutip
def test_benchmark_requires_one_time_grid() -> None:
    pytest.importorskip("qutip")
    with pytest.raises(ValueError, match="time grid"):
        run_page(
            _selection(
                simulators=[
                    {"simulator": "qutip", "time_steps": 3},
                    {"simulator": "qutip", "time_steps": 4},
                ]
            )
        )


def test_benchmark_rejects_a_simulator_that_is_not_an_object() -> None:
    with pytest.raises(ValueError, match="each simulator must be an object"):
        run_page(_selection(simulators=["qutip", "qutip"]))


@pytest.mark.qiskit
@pytest.mark.parametrize("simulator_id", ["trotterization", "splitjmatrix"])
def test_circuit_simulator_measures_x_expectation(simulator_id: str) -> None:
    pytest.importorskip("qiskit_aer")
    simulator = build_simulator(_selection(simulator=simulator_id, measure="x", sites=[1]))
    assert simulator.basis == "".join("X" if qubit == 1 else "Z" for qubit in range(simulator.num_qubits))


def test_post_runs_rejects_malformed_json() -> None:
    status, body = _post(b"not-json")
    payload = json.loads(body)
    assert status == 400
    assert payload["error"] == "request body must be JSON"


def test_post_runs_rejects_a_json_list() -> None:
    status, body = _post(b"[1]")
    payload = json.loads(body)
    assert status == 400
    assert payload["error"] == "request body must be a JSON object"


def test_post_elsewhere_is_not_found() -> None:
    status, _body = _post(b"{}", path="/other")
    assert status == 404


def test_post_runs_reports_a_simulator_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(selection: Mapping[str, object], output_root: object = None) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", explode)
    status, body = _post(json.dumps(_selection()).encode())
    payload = json.loads(body)
    assert status == 500
    assert payload == {"error": "internal error"}
    assert "boom" in capsys.readouterr().err
    assert b"boom" not in body


def test_listed_backends_reads_concrete_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("shadowsim.backends.aer")

    class CircuitBackend(Protocol):
        def run_counts(self) -> None: ...

    class AerCircuitBackend:
        """Run a circuit on Qiskit Aer and return shot counts."""

        def __init__(self) -> None:
            return None

        def run_counts(self) -> None:
            return None

    class BareCircuitBackend:
        def __init__(self) -> None:
            return None

        def run_counts(self) -> None:
            return None

    class NoteCircuitBackend:
        """Not executable."""

        def __init__(self) -> None:
            return None

    class NeededCircuitBackend:
        """Needs one argument."""

        def __init__(self, qubits: int, shots: int = 1, scale: int = 2) -> None:
            return None

        def run_counts(self) -> None:
            return None

    BareCircuitBackend.__doc__ = None
    for cls in (CircuitBackend, AerCircuitBackend, BareCircuitBackend, NoteCircuitBackend, NeededCircuitBackend):
        cls.__module__ = module.__name__
        setattr(module, cls.__name__, cls)

    def helper() -> None:
        return None

    module.helper = helper  # type: ignore[attr-defined]

    class Foreign:
        """Imported type."""

        def run_counts(self) -> None:
            return None

    Foreign.__module__ = "qiskit"
    module.Foreign = Foreign  # type: ignore[attr-defined]

    def fake_import(name: str, *, extra: str) -> types.ModuleType:
        if name != "shadowsim.backends.aer":
            raise ImportError(name)
        assert extra == "qiskit"
        return module

    monkeypatch.setattr("shadowsim.backends.catalog.import_optional", fake_import)
    assert listed_backends() == [
        {
            "id": "aer",
            "title": "Aer",
            "detail": "Run a circuit on Qiskit Aer and return shot counts.",
            "phrase": "Aer",
            "setup": "circuit_backend = AerCircuitBackend()",
            "shots": False,
            "fields": [],
        },
        {
            "id": "bare",
            "title": "Bare",
            "detail": "Bare",
            "phrase": "Bare",
            "setup": "circuit_backend = BareCircuitBackend()",
            "shots": False,
            "fields": [],
        },
        {
            "id": "needed",
            "title": "Needed",
            "detail": "Needs one argument.",
            "phrase": "Needed",
            "setup": "circuit_backend = NeededCircuitBackend(qubits, shots={shots}, scale={scale})",
            "shots": True,
            "fields": [{"name": "scale", "label": "scale", "default": "2", "allow_inf": False}],
        },
    ]


def test_listed_backends_reraises_the_first_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str, *, extra: str) -> types.ModuleType:
        raise ImportError(f"missing {name}")

    monkeypatch.setattr("shadowsim.backends.catalog.import_optional", fake_import)

    with pytest.raises(ImportError, match="missing shadowsim.backends.aer"):
        listed_backends()


def test_listed_backends_rejects_an_empty_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str, *, extra: str) -> types.ModuleType:
        return types.ModuleType(name)

    monkeypatch.setattr("shadowsim.backends.catalog.import_optional", fake_import)

    with pytest.raises(ImportError, match="no circuit backends"):
        listed_backends()


@pytest.mark.qiskit
def test_listed_backends_matches_the_circuit_module() -> None:
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")
    listed = listed_backends()
    assert [item["id"] for item in listed] == ["aer", "paulipropagation"]
    from shadowsim.backends.aer import AerCircuitBackend

    assert listed[0]["setup"] == "circuit_backend = AerCircuitBackend(shots={shots}, basis_gates={basis_gates})"
    assert listed[0]["shots"] is True
    assert listed[0]["fields"] == [
        {
            "name": "basis_gates",
            "label": "Gates",
            "default": "",
            "allow_inf": False,
            "kind": "gates",
            "choices": list(AerCircuitBackend.BASIS_GATE_NAMES),
        }
    ]
    assert "store" not in listed[0]["fields"][0]["choices"]
    assert "cx" in listed[0]["fields"][0]["choices"]
    assert "Aer" in listed[0]["detail"]
    assert listed[1]["setup"] == (
        "circuit_backend = PauliPropagationBackend(max_weight={max_weight}, min_abs_coeff={min_abs_coeff})"
    )
    assert listed[1]["shots"] is False
    assert listed[1]["fields"] == [
        {"name": "max_weight", "label": "Max weight", "default": "inf", "allow_inf": True},
        {"name": "min_abs_coeff", "label": "Min coefficient", "default": "1e-10", "allow_inf": False},
    ]
    assert "Pauli" in listed[1]["detail"]


def test_describe_models_formats_each_default_kind() -> None:
    module = types.ModuleType("shadowsim.models")

    def varied(
        *,
        text: str = "hi",
        count: int = 3,
        flag: bool = False,
        other: object = None,
        bare: float | Sequence = 1.0,
        old: Union[float, list[float]] = 1.0,
        mixed: Literal["a", 1] = "a",
    ) -> None:
        """Varied defaults."""

    varied.__module__ = "shadowsim.models.varied"
    module.__all__ = ["varied"]  # type: ignore[attr-defined]
    module.varied = varied  # type: ignore[attr-defined]
    params = {item["name"]: item for item in _describe_models(module)[0]["params"]}
    assert params["text"]["default"] == "hi"
    assert params["count"]["default"] == "3"
    assert params["flag"]["default"] == ""
    assert params["other"]["default"] == ""
    assert params["bare"]["kind"] == "number_or_list"
    assert params["old"]["kind"] == "number"
    assert params["mixed"]["kind"] == "choice"
    assert params["mixed"]["choices"] == ["a"]


def test_describe_models_reads_factories() -> None:
    module = types.ModuleType("shadowsim.models")

    def ising(*, n_qubits: int, h: float = 0.0) -> None:
        """Build a classical or transverse-field Ising model."""
        del n_qubits, h

    def odd(*, edges: int) -> None:
        """Odd ``model``."""
        del edges

    def bare() -> None:
        return None

    class IsingModel:
        """Not a factory."""

    def helper() -> None:
        """Defined outside the models package."""
        return None

    bare.__doc__ = None
    bare.__module__ = "shadowsim.models.bare"
    ising.__module__ = "shadowsim.models.ising"
    odd.__module__ = "shadowsim.models.odd"
    IsingModel.__module__ = "shadowsim.models.ising"
    helper.__module__ = "other"
    module.__all__ = ["IsingModel", "ising", "odd", "bare", "helper"]  # type: ignore[attr-defined]
    module.IsingModel = IsingModel  # type: ignore[attr-defined]
    module.ising = ising  # type: ignore[attr-defined]
    module.odd = odd  # type: ignore[attr-defined]
    module.bare = bare  # type: ignore[attr-defined]
    module.helper = helper  # type: ignore[attr-defined]

    assert _describe_models(module) == [
        {
            "id": "ising",
            "title": "Ising",
            "detail": "Build a classical or transverse-field Ising model.",
            "phrase": "Ising",
            "setup": "model = ising(n_qubits={qubits})",
            "qubits": True,
            "params": [{"name": "h", "label": "h", "kind": "number", "default": "0"}],
        },
        {
            "id": "odd",
            "title": "Odd",
            "detail": "Odd model.",
            "phrase": "Odd",
            "setup": "model = odd(edges)",
            "qubits": False,
            "params": [],
        },
        {
            "id": "bare",
            "title": "Bare",
            "detail": "Bare",
            "phrase": "Bare",
            "setup": "model = bare()",
            "qubits": False,
            "params": [],
        },
    ]


def _cavity_params(*, sequence: bool) -> list[dict[str, object]]:
    """Return the shared cavity-emitter chip fields."""
    varied = "number_or_list" if sequence else "number"
    return [
        {"name": "omega_c", "label": "omega_c", "kind": "number", "default": "245000"},
        {"name": "omega_e", "label": "omega_e", "kind": varied, "default": "245000"},
        {"name": "kappa", "label": "kappa", "kind": "number", "default": format(math.sqrt(24.5), ".16g")},
        {"name": "gamma", "label": "gamma", "kind": varied, "default": format(math.sqrt(0.4), ".16g")},
        {"name": "g", "label": "g", "kind": varied, "default": "100"},
    ]


def test_listed_models_reads_the_package_factories() -> None:
    listed = listed_models()
    assert [item["id"] for item in listed] == [
        "ising",
        "jaynes_cummings",
        "jaynes_cummings_hubbard",
        "tavis_cummings",
        "tavis_cummings_hubbard",
    ]
    assert listed[0]["title"] == "Ising"
    assert listed[0]["qubits"] is True
    assert listed[0]["setup"] == "model = ising(n_qubits={qubits})"
    assert listed[0]["params"] == [
        {"name": "J", "label": "J", "kind": "number", "default": "1"},
        {"name": "h", "label": "h", "kind": "number", "default": "0"},
        {
            "name": "field",
            "label": "field",
            "kind": "choice",
            "default": "transverse",
            "choices": ["classical", "transverse"],
        },
        {"name": "topology", "label": "topology", "kind": "choice", "default": "chain", "choices": ["chain"]},
        {
            "name": "boundary",
            "label": "boundary",
            "kind": "choice",
            "default": "open",
            "choices": ["open", "periodic"],
        },
        {"name": "edges", "label": "edges", "kind": "edges", "default": ""},
    ]
    scalars = _cavity_params(sequence=False)
    sequences = _cavity_params(sequence=True)
    assert listed[1]["title"] == "Jaynes-Cummings"
    assert listed[1]["qubits"] is False
    assert listed[1]["params"] == scalars
    assert listed[2]["title"] == "Jaynes-Cummings-Hubbard"
    assert listed[2]["qubits"] is False
    assert listed[2]["setup"] == "model = jaynes_cummings_hubbard()"
    assert listed[2]["params"] == scalars
    assert listed[3]["setup"] == "model = tavis_cummings()"
    assert listed[3]["params"] == sequences
    assert listed[4]["title"] == "Tavis-Cummings-Hubbard"
    assert listed[4]["qubits"] is False
    assert listed[4]["setup"] == "model = tavis_cummings_hubbard()"
    assert listed[4]["params"] == sequences
    skipped = {"n_qubits", "n_emitters", "n_cavities", "nu", "cavity_levels", "initial_fock"}
    for item in listed:
        assert skipped.isdisjoint(param["name"] for param in item["params"])
    kappa = next(param for param in scalars if param["name"] == "kappa")
    gamma = next(param for param in scalars if param["name"] == "gamma")
    assert float(kappa["default"]) == math.sqrt(24.5)
    assert float(gamma["default"]) == math.sqrt(0.4)


def test_listed_model_terms_reads_operator_classes() -> None:
    listed = listed_model_terms()
    assert [item["id"] for item in listed] == ["hamiltonian", "local_hamiltonian", "lindblad"]
    assert [item["title"] for item in listed] == [
        "Add a Hamiltonian",
        "Add a Local Hamiltonian",
        "Add a Lindblad operator",
    ]
    assert listed[0]["setup"] == "{name} = Hamiltonian(matrix)"
    assert listed[1]["setup"] == "{name} = LocalHamiltonian(matrix, sites)"
    assert listed[2]["setup"] == "{name} = Operator(matrix)"
    assert listed[0]["adds"] is True
    assert "Hamiltonian" in listed[0]["detail"]
    assert listed[2]["symbol"] == "Operator"


def test_listed_simulators_skips_imports_that_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim import simulators
    from shadowsim.simulators.simulator import Simulator

    class BareSimulator(Simulator):
        def __init__(self, hamiltonians: object) -> None:
            del hamiltonians

    class NoteSimulator(Simulator):
        """Simulate with a ``note``."""

        def __init__(self, observables: object) -> None:
            del observables

    class Plain:
        """Not a simulator."""

    BareSimulator.__doc__ = None
    module = types.ModuleType("shadowsim.simulators.fake")
    module.BareSimulator = BareSimulator  # type: ignore[attr-defined]
    module.NoteSimulator = NoteSimulator  # type: ignore[attr-defined]
    module.Plain = Plain  # type: ignore[attr-defined]
    module.Simulator = Simulator  # type: ignore[attr-defined]
    plain = types.ModuleType("plain.mod")
    plain.Widget = "nope"  # type: ignore[attr-defined]

    real_import_module = importlib.import_module

    def fake_import_module(name: str) -> types.ModuleType:
        if name == "plain.mod":
            return plain
        return real_import_module(name)

    def fake_optional(name: str, *, extra: str) -> types.ModuleType:
        assert extra == "qiskit"
        if name == "missing.simulator":
            raise ImportError("missing extra")
        return module

    monkeypatch.setattr(
        simulators,
        "_EXPORTS",
        {
            "Widget": ("plain.mod", None),
            "Gone": ("missing.simulator", "qiskit"),
            "Plain": ("shadowsim.simulators.fake", "qiskit"),
            "Simulator": ("shadowsim.simulators.fake", "qiskit"),
            "BareSimulator": ("shadowsim.simulators.fake", "qiskit"),
            "NoteSimulator": ("shadowsim.simulators.fake", "qiskit"),
        },
    )
    monkeypatch.setattr("shadowsim.simulators.catalog.importlib.import_module", fake_import_module)
    monkeypatch.setattr("shadowsim.simulators.catalog.import_optional", fake_optional)
    listed = listed_simulators()
    assert [item["id"] for item in listed] == ["bare", "note"]
    assert listed[0]["detail"] == "Base class for quantum simulation backends."
    assert listed[0]["observables"] is False
    assert listed[0]["samples"] is False
    assert "BareSimulator" in listed[0]["setup"]
    assert listed[1]["detail"] == "Simulate with a note."
    assert listed[1]["observables"] is True
    assert listed[1]["samples"] is False


def test_describe_simulator_uses_the_title_without_a_docstring(monkeypatch: pytest.MonkeyPatch) -> None:
    class BareSimulator:
        def __init__(self) -> None:
            return None

    monkeypatch.setattr("shadowsim.simulators.catalog.inspect.getdoc", lambda cls: None)
    described = _describe_simulator(BareSimulator)
    assert described["detail"] == "Bare"
    assert described["observables"] is False
    assert described["samples"] is False


def test_listed_simulators_fail_when_none_import(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim import simulators

    monkeypatch.setattr(simulators, "_EXPORTS", {"Gone": ("missing.simulator", "qiskit")})

    def explode(name: str, *, extra: str) -> types.ModuleType:
        del name, extra
        raise ImportError("missing extra")

    monkeypatch.setattr("shadowsim.simulators.catalog.import_optional", explode)
    with pytest.raises(ImportError, match="no simulators"):
        listed_simulators()


@pytest.mark.qutip
@pytest.mark.qiskit
def test_listed_simulators_reads_the_package_classes() -> None:
    pytest.importorskip("qutip")
    pytest.importorskip("qiskit_aer")
    listed = listed_simulators()
    assert [item["id"] for item in listed] == ["qutip", "splitjmatrix", "trotterization"]
    assert listed[0]["observables"] is True
    assert listed[0]["samples"] is False
    assert listed[0]["setup"].startswith("{name} = QutipSimulator")
    assert "{total}" in listed[0]["setup"]
    assert listed[1]["observables"] is False
    assert listed[1]["samples"] is True
    assert "SplitJMatrixSimulator" in listed[1]["setup"]
    assert listed[2]["samples"] is False
    assert "QuTiP" in listed[0]["detail"]


def test_get_models_returns_the_package_factories() -> None:
    status, body = _request("GET", "/models")
    payload = json.loads(body)
    assert status == 200
    assert [item["id"] for item in payload["models"]] == [
        "ising",
        "jaynes_cummings",
        "jaynes_cummings_hubbard",
        "tavis_cummings",
        "tavis_cummings_hubbard",
        "hamiltonian",
        "local_hamiltonian",
        "lindblad",
    ]


def test_get_simulators_reports_an_import_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode() -> list[object]:
        raise ImportError("no simulators could be imported")

    monkeypatch.setattr("shadowsim.cli.serve.listed_simulators", explode)
    status, body = _request("GET", "/simulators")
    payload = json.loads(body)
    assert status == 500
    assert payload == {"error": "internal error"}
    assert "no simulators could be imported" in capsys.readouterr().err
    assert b"no simulators" not in body


def test_get_backends_returns_the_package_list(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [
        {
            "id": "aer",
            "title": "Aer",
            "detail": "Run a circuit on Qiskit Aer and return shot counts.",
            "phrase": "Aer",
            "setup": "circuit_backend = AerCircuitBackend()",
        }
    ]
    monkeypatch.setattr("shadowsim.cli.serve.listed_backends", lambda: sample)
    status, body = _request("GET", "/backends")
    assert status == 200
    assert json.loads(body) == {"backends": sample}


def test_get_backends_reports_an_import_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode() -> list[object]:
        raise ImportError("/home/builder/shadowsim/backends/circuit.py requires the qiskit extra")

    monkeypatch.setattr("shadowsim.cli.serve.listed_backends", explode)
    status, body = _request("GET", "/backends")
    payload = json.loads(body)
    assert status == 500
    assert payload == {"error": "internal error"}
    assert "/home/builder/shadowsim/backends/circuit.py" in capsys.readouterr().err
    assert b"/home/builder" not in body


@pytest.mark.qutip
def test_post_runs_returns_traces() -> None:
    pytest.importorskip("qutip")
    status, body = _post(json.dumps(_selection()).encode())
    payload = json.loads(body)
    assert status == 200
    assert payload["algorithm"] == "qutip_simulator"
    assert isinstance(payload["runtime"], float)
    assert len(payload["times"]) == 101
    assert len(payload["observables"]) == 2
    assert payload["labels"] == ["⟨Z⟩ on 0", "⟨Z⟩ on 1"]
    resources = payload["resources"]
    assert len(resources) == 1
    assert resources[0]["simulator_id"] == "qutip_simulator"
    assert resources[0]["wall_time_s"] == payload["runtime"]
    assert resources[0]["shots_per_job"] is None
    assert resources[0]["num_jobs"] is None
    assert resources[0]["total_shots"] is None
    assert all(len(curve) == 101 for curve in payload["observables"])
    assert "states" not in payload


_Z_MATRIX = [[[1, 0], [0, 0]], [[0, 0], [-1, 0]]]
_JUMP = [[[0, 0], [1, 0]], [[0, 0], [0, 0]]]


def _added(**overrides: object) -> dict[str, object]:
    payload = _selection(
        model=None,
        qubits="1",
        basis="0",
        terms=[{"id": "hamiltonian", "matrix": _Z_MATRIX}],
    )
    payload.update(overrides)
    return payload


@pytest.mark.qutip
def test_added_hamiltonian_is_built_for_qutip() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_added())
    matrix = simulator.hamiltonians[0].matrix
    assert matrix.shape == (2, 2)
    assert matrix[0, 0] == 1
    assert matrix[1, 1] == -1


@pytest.mark.qutip
def test_added_local_hamiltonian_keeps_its_sites() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(
        _added(
            qubits="2",
            basis="00",
            terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [0]}],
        )
    )
    assert simulator.hamiltonians[0].sites == [0]


@pytest.mark.qutip
def test_added_lindblad_is_embedded_for_qutip() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(
        _added(terms=[{"id": "hamiltonian", "matrix": _Z_MATRIX}, {"id": "lindblad", "matrix": _JUMP, "sites": [0]}])
    )
    embedded = simulator.lindblads[0].matrix
    assert embedded.shape == (2, 2)
    assert embedded[0, 1] == 1
    assert embedded[1, 0] == 0


@pytest.mark.qiskit
def test_added_lindblad_stays_local_for_a_circuit() -> None:
    pytest.importorskip("qiskit")
    simulator = build_simulator(
        _added(
            simulator="splitjmatrix",
            terms=[{"id": "hamiltonian", "matrix": _Z_MATRIX}, {"id": "lindblad", "matrix": _JUMP, "sites": [0]}],
        )
    )
    assert simulator.hamiltonians[0].sites == [0]
    assert simulator.lindblads[0].sites == [0]
    assert simulator.lindblads[0].matrix[0, 1] == 1


def test_added_terms_fail_before_optional_imports(forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match="add a Hamiltonian"):
        build_simulator(_added(terms=[{"id": "lindblad", "matrix": _JUMP, "sites": [0]}]))
    with pytest.raises(ValueError, match="Hermitian"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": _JUMP}]))
    with pytest.raises(ValueError, match="square"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": [1, 0]}]))
    with pytest.raises(ValueError, match="contiguous"):
        build_simulator(
            _added(
                qubits="3",
                basis="000",
                terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [0, 2]}],
            )
        )
    with pytest.raises(ValueError, match="4×4"):
        build_simulator(
            _added(
                qubits="2",
                basis="00",
                terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [0, 1]}],
            )
        )


def test_ignored_actions_and_bad_numbers_fail_before_import(forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match="unknown simulator"):
        run_page(_selection(simulator="nope", thens=1))
    with pytest.raises(ValueError, match="unknown measurement"):
        build_simulator(_selection(simulator="trotterization", measure="y"))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(time_steps=True))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps=2.5))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps=float("nan")))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps="  "))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps="2.5"))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps="nan"))
    with pytest.raises(ValueError, match="time steps must be an integer"):
        build_simulator(_selection(simulator="trotterization", time_steps=None))
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        build_simulator(_selection(simulator="trotterization", time_steps=2.0, shots=0))


def test_added_operator_details_fail_before_import(forbid_qutip: None) -> None:
    bare = [[1, 2], [0, 1]]
    with pytest.raises(ValueError, match="from 1 to 8"):
        build_simulator(_added(qubits="0"))
    with pytest.raises(ValueError, match="from 1 to 8"):
        build_simulator(_added(qubits="9"))
    with pytest.raises(ValueError, match="operator objects"):
        build_simulator(_added(terms=["nope"]))
    with pytest.raises(ValueError, match="must be 4×4"):
        build_simulator(_added(qubits="2", basis="00", terms=[{"id": "hamiltonian", "matrix": _Z_MATRIX}]))
    with pytest.raises(ValueError, match="local Hamiltonian matrix must be Hermitian"):
        build_simulator(_added(terms=[{"id": "local_hamiltonian", "matrix": _JUMP, "sites": [0]}]))
    with pytest.raises(ValueError, match="unknown operator"):
        build_simulator(_added(terms=[{"id": "nope", "matrix": _Z_MATRIX}]))
    with pytest.raises(ValueError, match="square"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": [[[1, 0], [0, 0]], [[0, 0]]]}]))
    with pytest.raises(ValueError, match="power of two"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": [[[1, 0]]]}]))
    with pytest.raises(ValueError, match="Hermitian"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": bare}]))
    with pytest.raises(ValueError, match="finite numbers"):
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": [[True, 0], [0, 1]]}]))
    with pytest.raises(ValueError, match="finite numbers"):
        text_matrix = [[["nope", 0], [0, 0]], [[0, 0], [1, 0]]]
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": text_matrix}]))
    with pytest.raises(ValueError, match="finite numbers"):
        nan_matrix = [[[float("nan"), 0], [0, 0]], [[0, 0], [1, 0]]]
        build_simulator(_added(terms=[{"id": "hamiltonian", "matrix": nan_matrix}]))
    with pytest.raises(ValueError, match="non-empty list"):
        build_simulator(_added(terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": []}]))
    with pytest.raises(ValueError, match="indexes from 0 to 0"):
        build_simulator(_added(terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [1]}]))
    with pytest.raises(ValueError, match="indexes from 0 to 0"):
        build_simulator(_added(terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [True]}]))
    with pytest.raises(ValueError, match="unique"):
        build_simulator(_added(terms=[{"id": "local_hamiltonian", "matrix": _Z_MATRIX, "sites": [0, 0]}]))


def test_angle_list_rejects_non_finite_numbers(forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match="finite real numbers"):
        build_simulator(_selection(state="angle", angles=[True, 0.0]))
    with pytest.raises(ValueError, match="finite real numbers"):
        build_simulator(_selection(state="angle", angles=["0", 0.0]))
    with pytest.raises(ValueError, match="finite real numbers"):
        build_simulator(_selection(state="angle", angles=[float("nan"), 0.0]))


def test_trotterization_rejects_an_added_lindblad() -> None:
    with pytest.raises(ValueError, match="closed-system only"):
        build_simulator(
            _added(
                simulator="trotterization",
                terms=[{"id": "hamiltonian", "matrix": _Z_MATRIX}, {"id": "lindblad", "matrix": _JUMP, "sites": [0]}],
            )
        )
