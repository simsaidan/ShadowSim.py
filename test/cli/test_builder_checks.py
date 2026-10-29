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


def test_tavis_cummings_hubbard_preview_uses_cavities_and_hopping() -> None:
    page = _qutip_page()
    page["preexistingId"] = "tavis_cummings_hubbard"
    page["cavityText"] = "2"
    page["emitterText"] = "1"
    page["hoppingText"] = "1.5"
    page["basisBits"] = "000000"
    page["modelFactories"] = [
        {
            "id": "tavis_cummings_hubbard",
            "title": "Tavis-Cummings-Hubbard",
            "qubits": False,
            "setup": "model = tavis_cummings_hubbard()",
        }
    ]
    assert _call("hubbardSelected", page) is True
    assert _call("cavityModelSelected", page) is True
    assert _call("fixedFactoryQubits", page) == 6
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "from shadowsim.models import tavis_cummings_hubbard" in text
    assert "model = tavis_cummings_hubbard(n_cavities=2, n_emitters=1, nu=1.5)" in text

    page["emitterText"] = "6"
    assert _call("fixedFactoryQubits", page) is None
    assert _call("emitterProblem", page) is True
    assert _call("factoryAlert", page) == "Cavities and emitters must use at most 15 qubits"


def test_jaynes_cummings_hubbard_preview_uses_cavities_and_hopping() -> None:
    page = _qutip_page()
    page["preexistingId"] = "jaynes_cummings_hubbard"
    page["cavityText"] = "2"
    page["emitterText"] = "4"
    page["hoppingText"] = "1.5"
    page["basisBits"] = "000000"
    page["modelFactories"] = [
        {
            "id": "jaynes_cummings_hubbard",
            "title": "Jaynes-Cummings-Hubbard",
            "qubits": False,
            "setup": "model = jaynes_cummings_hubbard()",
        }
    ]
    assert _call("jaynesHubbardSelected", page) is True
    assert _call("hubbardSelected", page) is False
    assert _call("usesEmitterCount", page) is False
    assert _call("cavityModelSelected", page) is True
    assert _call("fixedFactoryQubits", page) == 6
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "from shadowsim.models import jaynes_cummings_hubbard" in text
    assert "model = jaynes_cummings_hubbard(n_cavities=2, nu=1.5)" in text
    assert "n_emitters" not in text

    page["cavityText"] = "6"
    assert _call("fixedFactoryQubits", page) is None
    assert _call("emitterProblem", page) is True
    assert _call("factoryAlert", page) == "Cavities must use at most 15 qubits"


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


_ISING_PARAMS = [
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


def test_ising_preview_includes_factory_arguments() -> None:
    page = _qutip_page()
    page["modelFactories"][0]["params"] = _ISING_PARAMS
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert 'model = ising(n_qubits=2, J=1.0, h=0.0, field="transverse", topology="chain", boundary="open")' in text
    assert "edges=" not in text

    page["settings"]["qubits"] = "4"
    page["basisBits"] = "0000"
    page["factoryText"] = {"J": "0.5", "edges": "0-1, 1-2"}
    edited = _call("previewText", page)
    assert isinstance(edited, str)
    assert "J=0.5" in edited
    assert "edges=[(0, 1), (1, 2)]" in edited
    assert 'boundary="open"' in edited


def test_bad_ising_arguments_block_the_run() -> None:
    page = _qutip_page()
    page["modelFactories"][0]["params"] = _ISING_PARAMS
    page["factoryText"] = {"J": "0", "h": "0"}
    assert _call("factoryAlert", page) == "J and h cannot both be zero"
    assert _call("runAllowed", page) is False

    page["factoryText"] = {"edges": "nope"}
    assert _call("factoryAlert", page) == "Enter edges as pairs such as 0-1, 1-2"
    assert _call("runAllowed", page) is False

    page["settings"]["qubits"] = "4"
    page["basisBits"] = "0000"
    page["factoryText"] = {"boundary": "periodic", "edges": "0-1"}
    assert _call("factoryAlert", page) == "Edges use the chain preset. Set topology to chain and boundary to open"
    assert _call("runAllowed", page) is False

    page["settings"]["qubits"] = "2"
    page["basisBits"] = "00"
    page["factoryText"] = {"boundary": "periodic"}
    assert _call("factoryAlert", page) == "Periodic boundary needs at least 3 qubits"
    assert _call("runAllowed", page) is False


def test_per_emitter_list_must_match_the_emitter_count() -> None:
    page = _qutip_page()
    page["preexistingId"] = "tavis_cummings"
    page["emitterText"] = "2"
    page["basisBits"] = "0000"
    page["modelFactories"] = [
        {
            "id": "tavis_cummings",
            "title": "Tavis-Cummings",
            "qubits": False,
            "setup": "model = tavis_cummings()",
            "params": [
                {"name": "omega_c", "label": "omega_c", "kind": "number", "default": "245000"},
                {"name": "omega_e", "label": "omega_e", "kind": "number_or_list", "default": "245000"},
                {"name": "kappa", "label": "kappa", "kind": "number", "default": "1"},
                {"name": "gamma", "label": "gamma", "kind": "number_or_list", "default": "1"},
                {"name": "g", "label": "g", "kind": "number_or_list", "default": "100"},
            ],
        }
    ]
    page["factoryText"] = {"g": "10, 20"}
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "model = tavis_cummings(n_emitters=2, omega_c=245000.0" in text
    assert "g=[10.0, 20.0]" in text

    page["factoryText"] = {"g": "1, 2, 3"}
    assert _call("factoryAlert", page) == "Enter 2 numbers for g"
    assert _call("runAllowed", page) is False


def test_hubbard_preview_keeps_structure_and_factory_arguments() -> None:
    page = _qutip_page()
    page["preexistingId"] = "tavis_cummings_hubbard"
    page["cavityText"] = "2"
    page["emitterText"] = "1"
    page["hoppingText"] = "1.5"
    page["basisBits"] = "000000"
    page["factoryText"] = {"omega_c": "10"}
    page["modelFactories"] = [
        {
            "id": "tavis_cummings_hubbard",
            "title": "Tavis-Cummings-Hubbard",
            "qubits": False,
            "setup": "model = tavis_cummings_hubbard()",
            "params": [
                {"name": "omega_c", "label": "omega_c", "kind": "number", "default": "245000"},
                {"name": "g", "label": "g", "kind": "number_or_list", "default": "100"},
            ],
        }
    ]
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "model = tavis_cummings_hubbard(n_cavities=2, n_emitters=1, nu=1.5, omega_c=10.0, g=100.0)" in text
