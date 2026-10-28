"""Tests for builder readiness and the code preview."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

CHECKS = Path(__file__).resolve().parents[2] / "shadowsim" / "cli" / "site" / "checks.js"

_SCRIPT = r"""
const checks = require(process.argv[1]);
const request = JSON.parse(process.argv[2]);
const value = checks[request.fn](request.page, ...request.args);
process.stdout.write(JSON.stringify(value));
"""

_LANES = [
    {"id": "state"},
    {"id": "model"},
    {"id": "simulator"},
    {"id": "measure"},
    {"id": "then"},
]


def _call(fn: str, page: dict[str, Any], *args: object) -> Any:
    """Return one exported check for ``page``."""
    request = {"fn": fn, "page": page, "args": list(args)}
    try:
        completed = subprocess.run(
            ["node", "-e", _SCRIPT, str(CHECKS), json.dumps(request)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        pytest.fail(f"node is required to test the builder checks: {exc}")
    if completed.returncode != 0:
        pytest.fail(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def _qutip_page() -> dict[str, Any]:
    """Return a complete QuTiP selection with no backend."""
    return {
        "lanes": _LANES,
        "blocks": {
            "state": [{"id": "basis", "title": "Basis state", "phrase": "Basis state"}],
            "model": [],
            "simulator": [{"id": "qutip", "title": "QuTiP", "observables": True}],
            "backend": [
                {
                    "id": "aer",
                    "phrase": "Aer",
                    "shots": True,
                    "setup": "circuit_backend = AerCircuitBackend(shots={shots})",
                }
            ],
            "measure": [{"id": "z", "title": "Z expectation", "phrase": "Z expectation on each qubit"}],
            "then": [
                {"id": "plot", "title": "Plot results", "phrase": "plot results"},
                {"id": "save", "title": "Save results", "phrase": "save results"},
                {"id": "export", "title": "Export metrics", "phrase": "export metrics"},
            ],
        },
        "selection": {
            "state": "basis",
            "model": "preexisting",
            "simulator": "qutip",
            "backend": None,
            "measure": "z",
            "then": "plot",
        },
        "settings": {"qubits": "2", "total": "1"},
        "modelTerms": [],
        "modelFactories": [
            {"id": "ising", "title": "Ising", "qubits": True, "setup": "model = ising(n_qubits={qubits})"}
        ],
        "preexistingId": "ising",
        "emitterText": "1",
        "basisBits": "00",
        "grayBits": "",
        "angleText": "",
        "amplitudeText": "",
        "placedSims": [{"id": "qutip", "params": {"timeSteps": "11"}}],
        "placedThens": ["plot"],
        "savePath": "results/run1",
        "exportPath": "results",
        "measureSites": None,
        "shots": "256",
        "qubitsSource": None,
        "stateLimits": {"basis": 15, "gray": 15, "angle": 15, "amplitude": 16},
        "maxEmitters": 13,
        "maxOperatorQubits": 8,
    }


def _circuit_page() -> dict[str, Any]:
    """Return a complete circuit selection, including a backend."""
    page = _qutip_page()
    page["blocks"]["simulator"] = [{"id": "trotterization", "title": "Trotterization", "observables": False}]
    page["selection"]["simulator"] = "trotterization"
    page["placedSims"] = [
        {
            "id": "trotterization",
            "params": {
                "timeSteps": "11",
                "numSteps": "4",
                "trotterDepth": "1",
                "seed": "0",
                "order": "1",
            },
            "backend": "aer",
            "shots": "256",
        }
    ]
    return page


@pytest.mark.parametrize("total", ["0", "-1"])
def test_non_positive_total_time_is_not_ready(total: str) -> None:
    page = _qutip_page()
    page["settings"]["total"] = total
    assert _call("settingsReady", page) is False
    assert _call("runAllowed", page) is False


def test_fractional_qubits_are_not_ready() -> None:
    page = _qutip_page()
    page["settings"]["qubits"] = "1.5"
    assert _call("settingsReady", page) is False
    assert _call("runAllowed", page) is False


def test_qutip_without_a_backend_is_ready() -> None:
    page = _qutip_page()
    assert page["selection"]["backend"] is None
    assert _call("runAllowed", page) is True


def test_circuit_simulator_without_a_backend_is_not_ready() -> None:
    page = _circuit_page()
    assert _call("runAllowed", page) is True
    page["placedSims"][0]["backend"] = None
    assert _call("runAllowed", page) is False
    assert _call("socketStatus", page, False) == "Snap a backend onto each simulator."


def test_circuit_row_without_shots_is_not_ready() -> None:
    page = _circuit_page()
    page["placedSims"][0]["shots"] = ""
    assert _call("shotsReady", page) is False
    assert _call("runAllowed", page) is False


def test_split_j_rejects_a_backend_without_shots() -> None:
    page = _circuit_page()
    page["blocks"]["simulator"] = [
        {"id": "splitjmatrix", "title": "SplitJMatrix", "observables": False, "samples": True},
        {"id": "trotterization", "title": "Trotterization", "observables": False, "samples": False},
    ]
    page["blocks"]["backend"].append(
        {
            "id": "paulipropagation",
            "phrase": "PauliPropagation",
            "shots": False,
            "setup": "circuit_backend = PauliPropagationBackend()",
        }
    )
    split_j = {"id": "splitjmatrix"}
    trotter = {"id": "trotterization"}
    assert _call("backendFits", page, split_j, "paulipropagation") is False
    assert _call("backendFits", page, split_j, "aer") is True
    assert _call("backendFits", page, trotter, "paulipropagation") is True
    assert _call("backendFits", page, {"id": "qutip"}, "aer") is False


def test_preview_names_a_backend_for_each_circuit_row() -> None:
    page = _circuit_page()
    page["blocks"]["simulator"] = [
        {"id": "trotterization", "title": "Trotterization", "observables": False, "samples": False},
        {"id": "splitjmatrix", "title": "SplitJMatrix", "observables": False, "samples": True},
    ]
    page["blocks"]["backend"].append(
        {
            "id": "paulipropagation",
            "phrase": "PauliPropagation",
            "shots": False,
            "setup": (
                "circuit_backend = PauliPropagationBackend(max_weight={max_weight}, min_abs_coeff={min_abs_coeff})"
            ),
            "fields": [
                {"name": "max_weight", "label": "Max weight", "default": "inf", "allow_inf": True},
                {"name": "min_abs_coeff", "label": "Min coefficient", "default": "1e-10", "allow_inf": False},
            ],
        }
    )
    first = page["placedSims"][0]
    first["backend"] = "paulipropagation"
    first["backendFields"] = {"max_weight": "inf", "min_abs_coeff": "1e-10"}
    second = {
        "id": "splitjmatrix",
        "params": dict(first["params"]),
        "backend": "aer",
        "shots": "128",
    }
    page["placedSims"] = [first, second]
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "from shadowsim.backends import PauliPropagationBackend, AerCircuitBackend" in text
    assert 'circuit_backend_1 = PauliPropagationBackend(max_weight=float("inf"), min_abs_coeff=1e-10)' in text
    assert "circuit_backend_2 = AerCircuitBackend(shots=128)" in text
    assert "circuit_backend=circuit_backend_1" in text
    assert "circuit_backend=circuit_backend_2" in text
    assert _call("entryBody", page, first)["backend"] == "paulipropagation"
    assert _call("entryBody", page, first)["max_weight"] == "inf"
    assert _call("entryBody", page, first)["min_abs_coeff"] == "1e-10"
    assert "shots" not in _call("entryBody", page, first)
    first["backendFields"] = {"max_weight": "", "min_abs_coeff": "1e-10"}
    assert _call("backendFieldsReady", page) is False
    assert _call("runAllowed", page) is False
    assert _call("entryBody", page, second) == {
        "simulator": "splitjmatrix",
        "time_steps": "11",
        "num_steps": "4",
        "trotter_depth": "1",
        "seed": "0",
        "order": "1",
        "backend": "aer",
        "shots": "128",
    }


def test_preview_numbers_a_backend_with_its_row() -> None:
    page = _circuit_page()
    page["blocks"]["simulator"].insert(0, {"id": "qutip", "title": "QuTiP", "observables": True})
    page["placedSims"].insert(0, {"id": "qutip", "params": {"timeSteps": "11"}})
    page["selection"]["simulator"] = "qutip"
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "circuit_backend_1" not in text
    assert "circuit_backend_2 = AerCircuitBackend(shots=256)" in text
    assert "circuit_backend=circuit_backend_2" in text
    qutip = _call("entryBody", page, page["placedSims"][0])
    assert qutip == {"simulator": "qutip", "time_steps": "11"}


def test_single_export_includes_the_metrics_call() -> None:
    page = _qutip_page()
    page["selection"]["then"] = "export"
    page["placedThens"] = ["export"]
    page["exportPath"] = "results"
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "save_resource_metrics(sim, result.runtime, output_dir=" in text
    assert "save_error_metrics" not in text


def test_benchmark_export_includes_save_error_metrics() -> None:
    page = _qutip_page()
    page["selection"]["then"] = "export"
    page["placedThens"] = ["export"]
    page["exportPath"] = "results/metrics.json"
    page["placedSims"] = [
        {"id": "qutip", "params": {"timeSteps": "11"}},
        {"id": "qutip", "params": {"timeSteps": "11"}},
    ]
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert 'benchmark.save_error_metrics(path="results/metrics.json")' in text


def test_preview_imports_are_explicit() -> None:
    qutip = _call("previewText", _qutip_page())
    assert isinstance(qutip, str)
    assert "from shadowsim.encoding import ComputationalBasisEncoding" in qutip
    assert "from shadowsim.simulators import QutipSimulator\n" in qutip
    assert "expectation_z" not in qutip
    assert "import *" not in qutip

    circuit = _call("previewText", _circuit_page())
    assert isinstance(circuit, str)
    assert "from shadowsim.simulators import TrotterizationSimulator, expectation_z" in circuit
    assert "import *" not in circuit

    measured = _circuit_page()
    measured["selection"]["measure"] = "x"
    measured["blocks"]["measure"].append({"id": "x", "title": "X expectation", "phrase": "X expectation on each qubit"})
    text = _call("previewText", measured)
    assert isinstance(text, str)
    assert "from shadowsim.simulators import TrotterizationSimulator, expectation_x" in text
    assert "expectation_z" not in text


def test_hamiltonian_problems_use_different_messages() -> None:
    page = _qutip_page()
    page["settings"]["qubits"] = "1"
    nonhermitian = _call(
        "hamiltonianProblem",
        page,
        {"id": "hamiltonian", "matrix": "[[1, 1], [0, 1]]"},
    )
    page["settings"]["qubits"] = "2"
    wrong_size = _call(
        "hamiltonianProblem",
        page,
        {"id": "hamiltonian", "matrix": "[[1, 0], [0, -1]]"},
    )
    assert nonhermitian == "Matrix must be Hermitian."
    assert wrong_size == "Must be 4\u00d74 for 2 qubits."
    assert nonhermitian != wrong_size
