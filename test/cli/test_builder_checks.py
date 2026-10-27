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
    {"id": "backend"},
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
    page["selection"]["backend"] = "aer"
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
    page["selection"]["backend"] = None
    assert _call("runAllowed", page) is False


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
    assert wrong_size == "Must be 4×4 for 2 qubits."
    assert nonhermitian != wrong_size
