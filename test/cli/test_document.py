"""Tests for research-CLI run document helpers."""

import json
from pathlib import Path

import pytest

from shadowsim.cli.document import (
    actions_section,
    build_run_document,
    expand_compare_backends,
    load_document,
    model_section,
    model_stub,
    parse_id_list,
    simulator_entry,
)
from shadowsim.cli.run import check_page


def test_parse_id_list_splits_and_strips() -> None:
    assert parse_id_list("numpy, aer, qulacs") == ["numpy", "aer", "qulacs"]
    with pytest.raises(ValueError, match="comma-separated"):
        parse_id_list(" , , ")


def test_model_section_fills_n_qubits_for_ising() -> None:
    assert model_section("ising", qubits=4, arguments={"J": 1.0}) == {
        "id": "ising",
        "arguments": {"J": 1.0, "n_qubits": 4},
    }
    with pytest.raises(ValueError, match="unknown model"):
        model_section("nope")


@pytest.mark.circuits
def test_simulator_entry_and_compare_validation() -> None:
    entry = simulator_entry(
        "trotterization",
        arguments={"time_steps": 5, "num_steps": 4},
        backend_id="numpy",
    )
    assert entry == {
        "id": "trotterization",
        "arguments": {"time_steps": 5, "num_steps": 4},
        "backend": {"id": "numpy", "arguments": {}},
    }
    with pytest.raises(ValueError, match="at least two backends"):
        expand_compare_backends("trotterization", ["numpy"])
    with pytest.raises(ValueError, match="unique"):
        expand_compare_backends("trotterization", ["numpy", "numpy"])


@pytest.mark.circuits
@pytest.mark.qiskit
@pytest.mark.cross_extra
def test_compare_expansion_across_backends() -> None:
    expanded = expand_compare_backends(
        "trotterization",
        ["numpy", "aer"],
        simulator_arguments={"time_steps": 5},
        backend_arguments={"shots": 128},
    )
    assert [item["backend"]["id"] for item in expanded] == ["numpy", "aer"]
    assert expanded[1]["backend"]["arguments"] == {"shots": 128}


@pytest.mark.circuits
def test_build_run_document_simulate_shape_passes_check_page() -> None:
    document = build_run_document(
        model="ising",
        qubits=2,
        simulator="trotterization",
        simulator_arguments={"time_steps": 2, "num_steps": 1},
        backend="numpy",
        total="0.5",
        measure="model",
        action_ids=[],
    )
    assert document["state"]["value"] == "00"
    assert check_page(document)["qubits"] == 2


def test_build_run_document_compare_rejects_backend_and_backends() -> None:
    with pytest.raises(ValueError, match="backend or backends"):
        build_run_document(
            model="ising",
            qubits=2,
            simulator="trotterization",
            backend="numpy",
            backends=["numpy", "aer"],
        )


@pytest.mark.circuits
@pytest.mark.qiskit
@pytest.mark.cross_extra
def test_build_run_document_compare_expands_backends() -> None:
    document = build_run_document(
        model="ising",
        qubits=2,
        simulator="trotterization",
        simulator_arguments={"time_steps": 2, "num_steps": 1},
        backends=["numpy", "aer"],
        action_ids=[],
    )
    assert len(document["simulators"]) == 2
    assert check_page(document)["qubits"] == 2


def test_actions_section_infers_ids_from_paths() -> None:
    assert actions_section(save_path="results/run1", export_path="results/out.json") == {
        "ids": ["save", "export"],
        "save_path": "results/run1",
        "export_path": "results/out.json",
    }
    assert actions_section(export_path="results/out.json") == {
        "ids": ["export"],
        "export_path": "results/out.json",
    }
    assert actions_section(save_path="results/run1") == {
        "ids": ["save"],
        "save_path": "results/run1",
    }
    with pytest.raises(ValueError, match="unknown action"):
        actions_section(action_ids=["nope"])


def test_model_stub_is_model_only() -> None:
    stub = model_stub("ising", qubits=3, arguments={"h": 0.5})
    assert stub == {
        "version": 1,
        "model": {"id": "ising", "arguments": {"h": 0.5, "n_qubits": 3}},
    }


@pytest.mark.circuits
def test_load_document_json(tmp_path: Path) -> None:
    document = build_run_document(
        model="ising",
        qubits=2,
        simulator="trotterization",
        simulator_arguments={"time_steps": 2, "num_steps": 1},
        backend="numpy",
        action_ids=[],
    )
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert load_document(path) == document


def test_load_document_rejects_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "experiment.txt"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported document type"):
        load_document(path)


def test_load_document_yaml_without_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "experiment.yaml"
    path.write_text("version: 1\n", encoding="utf-8")

    def missing(module: str, *, extra: str) -> object:
        raise ImportError(f"{module} requires the {extra} extra. Install it with: pip install 'shadowsim[{extra}]'")

    monkeypatch.setattr("shadowsim.cli.document.import_optional", missing)
    with pytest.raises(ImportError, match="shadowsim\\[yaml\\]"):
        load_document(path)


@pytest.mark.circuits
def test_load_document_yaml_when_available(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    document = build_run_document(
        model="ising",
        qubits=2,
        simulator="trotterization",
        simulator_arguments={"time_steps": 2, "num_steps": 1},
        backend="numpy",
        action_ids=[],
    )
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    assert load_document(path)["model"]["id"] == "ising"


@pytest.mark.qutip
def test_simulator_entry_allows_missing_backend() -> None:
    entry = simulator_entry("qutip", arguments={"time_steps": 2})
    assert entry["backend"] is None


def test_build_document_rejects_empty_simulators() -> None:
    from shadowsim.cli.document import build_document, model_section

    with pytest.raises(ValueError, match="non-empty list"):
        build_document(model=model_section("ising", qubits=2), simulators=[])


@pytest.mark.circuits
def test_build_document_measure_expression_and_actions() -> None:
    from shadowsim.cli.document import build_document, model_section

    document = build_document(
        model=model_section("ising", qubits=2),
        simulators=[simulator_entry("trotterization", backend_id="numpy")],
        measure_id="counts",
        measure_expression="p0",
        actions=actions_section(action_ids=["plot"]),
    )
    assert document["measure"]["expression"] == "p0"
    assert document["actions"]["ids"] == ["plot"]


def test_load_document_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "experiment.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        load_document(path)


def test_document_catalog_lookups_reject_unknown_ids() -> None:
    from shadowsim.cli import document

    with pytest.raises(ValueError, match="unknown simulator"):
        document._simulator_record("nope")
    with pytest.raises(ValueError, match="unknown backend"):
        document._backend_record("nope")
    with pytest.raises(ValueError, match="unknown initial state"):
        document._state_record("nope")
    with pytest.raises(ValueError, match="unknown measurement"):
        document._measurement_record("nope")


def test_n_qubits_and_default_state_helpers() -> None:
    from shadowsim.cli import document

    assert document._n_qubits({"arguments": {"n_qubits": "4"}}) == 4
    assert document._n_qubits({"arguments": {"n_qubits": True}}) is None
    assert document._n_qubits({"arguments": {"n_qubits": "x"}}) is None
    assert document._n_qubits({"arguments": None}) is None
    assert document._default_state_value("basis", None) is None
    assert document._default_state_value("basis", 0) is None
    assert document._default_state_value("gray", 3) == "000"
    assert document._default_state_value("angle", 2) is None
