"""Tests for research CLI commands and entry-point dispatch."""

import json
from pathlib import Path

import pytest

from shadowsim.cli.document import build_run_document
from shadowsim.cli.main import build_parser, main


def _simulate_argv(*extra: str) -> list[str]:
    return [
        "simulate",
        "--model",
        "ising",
        "--qubits",
        "2",
        "--simulator",
        "trotterization",
        "--time-steps",
        "2",
        "--num-steps",
        "1",
        "--backend",
        "numpy",
        *extra,
    ]


def _compare_argv(*extra: str) -> list[str]:
    return [
        "compare",
        "--model",
        "ising",
        "--qubits",
        "2",
        "--simulator",
        "trotterization",
        "--time-steps",
        "2",
        "--num-steps",
        "1",
        "--backends",
        "numpy,aer",
        *extra,
    ]


def test_build_parser_registers_research_commands() -> None:
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert set(choices) == {"serve", "model", "simulate", "compare", "run"}
    samples = {
        "serve": ["serve", "--no-browser"],
        "model": ["model", "ising"],
        "simulate": _simulate_argv(),
        "compare": _compare_argv(),
        "run": ["run", "experiment.json"],
    }
    for name, argv in samples.items():
        args = parser.parse_args(argv)
        assert args.command == name
        assert callable(args.handler)


def test_model_prints_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["model", "ising", "--qubits", "3", "--J", "1.0"]) == 0
    text = capsys.readouterr().out
    assert "model: ising" in text
    assert "n_qubits: 3" in text
    assert "J: 1.0" in text

    assert main(["model", "ising", "--qubits", "2", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"]["id"] == "ising"
    assert payload["model"]["arguments"]["n_qubits"] == 2


def test_model_defaults_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["model", "ising"]) == 0
    assert "arguments: (defaults)" in capsys.readouterr().out


def test_main_maps_model_argument_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["model", "ising", "--nu", "1.0"]) == 1
    assert "model ising does not take nu" in capsys.readouterr().err


def test_simulate_print_document_skips_run_page(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("run_page should not run")

    monkeypatch.setattr("shadowsim.cli.commands.run_page", boom)
    assert main([*_simulate_argv(), "--print-document"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["model"]["id"] == "ising"
    assert document["simulators"][0]["backend"]["id"] == "numpy"


def test_simulate_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_simulate_argv("--format", "text")) == 0
    text = capsys.readouterr().out
    assert "algorithm:" in text
    assert "labels:" in text

    assert main(_simulate_argv("--format", "json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "labels" in payload
    assert "resources" in payload


def test_simulate_save_under_output_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save_to = tmp_path / "run1"
    assert (
        main(
            _simulate_argv(
                "--save",
                str(save_to),
                "--output-dir",
                str(tmp_path),
                "--format",
                "text",
            )
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "saved:" in out
    assert save_to.exists()


def test_compare_runs_benchmark(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_compare_argv("--format", "text")) == 0
    out = capsys.readouterr().out
    assert "algorithm: benchmark" in out
    assert "errors:" in out


def test_compare_rejects_a_single_backend(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*_compare_argv()[:-1], "numpy"]) == 1
    assert "at least two backends" in capsys.readouterr().err


def test_run_loads_json_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    assert main(["run", str(path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "labels" in payload


def test_run_print_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps({"version": 1, "model": {"id": "ising", "arguments": {}}}), encoding="utf-8")
    assert main(["run", str(path), "--print-document"]) == 0
    assert json.loads(capsys.readouterr().out)["model"]["id"] == "ising"


def test_run_missing_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert main(["run", str(missing)]) == 1
    assert "error:" in capsys.readouterr().err


def test_simulate_rejects_unknown_simulator_field(capsys: pytest.CaptureFixture[str]) -> None:
    # qutip only takes time_steps among chip fields; seed is invalid for it.
    assert (
        main(
            [
                "simulate",
                "--model",
                "ising",
                "--qubits",
                "2",
                "--simulator",
                "qutip",
                "--time-steps",
                "2",
                "--seed",
                "1",
            ]
        )
        == 1
    )
    assert "simulator qutip does not take seed" in capsys.readouterr().err


def test_simulate_parses_state_value_and_sites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake_run(document: dict[str, object], *, output_root: object = None) -> dict[str, object]:
        seen["document"] = document
        return {
            "algorithm": "trotterization_simulator",
            "labels": ["z"],
            "resources": [{"title": "sim", "wall_time_s": 0.1, "shots": 10}],
            "saved": "results/run1",
            "exported": "results/metrics.json",
            "runtime": 0.1,
            "errors": [{"challenger_id": "x"}],
        }

    monkeypatch.setattr("shadowsim.cli.commands.run_page", fake_run)
    assert (
        main(
            [
                "simulate",
                "--model",
                "ising",
                "--qubits",
                "2",
                "--simulator",
                "trotterization",
                "--time-steps",
                "2",
                "--num-steps",
                "1",
                "--backend",
                "numpy",
                "--state",
                "basis",
                "--state-value",
                "01",
                "--measure",
                "z",
                "--sites",
                "0,1",
                "--shots",
                "32",
                "--format",
                "text",
            ]
        )
        == 0
    )
    document = seen["document"]
    assert isinstance(document, dict)
    assert document["state"]["value"] == "01"
    assert document["measure"]["sites"] == [0, 1]
    assert document["simulators"][0]["backend"]["arguments"]["shots"] == 32
    out = capsys.readouterr().out
    assert "saved: results/run1" in out
    assert "exported: results/metrics.json" in out
    assert "errors:" in out


def test_simulate_parses_json_state_and_sites(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(document: dict[str, object], *, output_root: object = None) -> dict[str, object]:
        seen["document"] = document
        return {"labels": []}

    monkeypatch.setattr("shadowsim.cli.commands.run_page", fake_run)
    assert (
        main(
            [
                "simulate",
                "--model",
                "ising",
                "--qubits",
                "2",
                "--simulator",
                "trotterization",
                "--time-steps",
                "2",
                "--num-steps",
                "1",
                "--backend",
                "numpy",
                "--state",
                "angle",
                "--state-value",
                "[0.1, 0.2]",
                "--sites",
                "[0]",
                "--format",
                "json",
            ]
        )
        == 0
    )
    document = seen["document"]
    assert isinstance(document, dict)
    assert document["state"]["value"] == [0.1, 0.2]
    assert document["measure"]["sites"] == [0]


def test_format_text_falls_back_for_empty_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shadowsim.cli.commands.run_page", lambda *_a, **_k: {})
    assert main(_simulate_argv("--format", "text")) == 0
    assert capsys.readouterr().out.strip() == "{}"


def test_catalog_helpers_tolerate_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim.cli import commands

    monkeypatch.setattr(
        commands,
        "listed_simulators",
        lambda: (_ for _ in ()).throw(ImportError("no simulators")),
    )
    monkeypatch.setattr(
        commands,
        "listed_backends",
        lambda: (_ for _ in ()).throw(ImportError("no backends")),
    )
    assert commands._simulator_ids() == []
    assert commands._backend_ids() == []
    assert commands._simulator_field_names() == []
    assert commands._backend_field_names() == []


def test_unknown_simulator_record_raises() -> None:
    from shadowsim.cli import commands

    with pytest.raises(ValueError, match="unknown simulator"):
        commands._simulator_record("nope")


def test_parse_helpers_cover_non_string_inputs() -> None:
    from shadowsim.cli import commands

    assert commands._parse_state_value(None) is None
    assert commands._parse_state_value([1.0, 0.0]) == [1.0, 0.0]
    assert commands._parse_sites(None) is None
    assert commands._parse_sites([0, 1]) == [0, 1]
    assert commands._parse_sites("  ") is None


def test_format_text_skips_non_mapping_resources() -> None:
    from shadowsim.cli import commands

    text = commands._format_text(
        {
            "resources": ["skip", {"title": "only-title"}],
        }
    )
    assert "only-title:" in text
    assert "skip" not in text


def test_backend_field_flags_skip_shots_name(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from shadowsim.cli import commands

    monkeypatch.setattr(commands, "_backend_field_names", lambda: ["shots", "basis_gates"])
    parser = argparse.ArgumentParser()
    commands._add_backend_field_flags(parser)
    args = parser.parse_args(["--shots", "8", "--basis-gates", "x,y"])
    assert args.shots == 8
    assert args.basis_gates == "x,y"


def test_unknown_model_record_raises() -> None:
    from shadowsim.cli import commands

    with pytest.raises(ValueError, match="unknown model"):
        commands._model_record("nope")


def test_save_and_export_infer_action_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(document: dict[str, object], *, output_root: object = None) -> dict[str, object]:
        seen["document"] = document
        return {"labels": ["z"]}

    monkeypatch.setattr("shadowsim.cli.commands.run_page", fake_run)
    assert (
        main(
            _simulate_argv(
                "--save",
                "results/run1",
                "--export",
                "results/out.json",
                "--format",
                "json",
            )
        )
        == 0
    )
    document = seen["document"]
    assert isinstance(document, dict)
    assert document["actions"]["ids"] == ["save", "export"]
