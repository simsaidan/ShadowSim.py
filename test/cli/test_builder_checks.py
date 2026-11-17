"""Run the generated circuit previews under Qiskit.

The other builder checks live in ``test/js/checks.test.js``. These two stay
here because they execute the preview as Python.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from shadowsim.cli.catalog import listed_actions, listed_measurements, listed_states
from shadowsim.cli.run import _page_limits

CHECKS = Path(__file__).resolve().parents[2] / "shadowsim" / "cli" / "site" / "checks.js"
_SCRIPT = """
const { readFileSync } = require("node:fs");
const checks = require(process.argv[1]);
const request = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(checks[request.fn](request.page, ...request.args)));
"""

_QUTIP_SETUP = (
    "{name} = QutipSimulator({hamiltonians}, {lindblads}, state,\n"
    "                    e_ops, num_qubits={qubits},\n"
    "                    total_time={total}, time_steps={time_steps})"
)

_LANES = [
    {"id": "state"},
    {"id": "model"},
    {"id": "simulator"},
    {"id": "measure"},
    {"id": "then"},
]


def _circuit_setup(class_name: str) -> str:
    """Return the catalog setup string for one circuit simulator."""
    return (
        f"{{name}} = {class_name}(\n"
        "    {hamiltonians},\n"
        "    {lindblads},\n"
        "    state,\n"
        "    num_qubits={qubits},\n"
        "    total_time={total},\n"
        "    time_steps={time_steps},\n"
        "    num_steps={num_steps},\n"
        "    trotter_depth={trotter_depth},\n"
        "    order={order},\n"
        "    seed={seed}{basis},\n"
        "    circuit_backend={backend},\n"
        ")"
    )


def _call(fn: str, page: dict[str, Any], *args: object) -> Any:
    """Return one exported check for ``page``."""
    request = json.dumps({"fn": fn, "page": page, "args": list(args)})
    try:
        completed = subprocess.run(
            ["node", "-e", _SCRIPT, str(CHECKS)],
            input=request,
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


def _chip(
    name: str,
    label: str,
    default: str,
    maximum: str | None = None,
    choices: list[str] | None = None,
) -> dict[str, object]:
    """Return one simulator chip field. ``maximum`` is a key of :func:`_page_limits`."""
    if choices is not None:
        return {"name": name, "label": label, "kind": "choice", "default": default, "choices": choices}
    field: dict[str, object] = {"name": name, "label": label, "kind": "integer", "default": default}
    if maximum is not None:
        field["minimum"] = 1
        field["maximum"] = _page_limits()[maximum]
    return field


def _qutip_fields() -> list[dict[str, object]]:
    """Return the time-step field a QuTiP card edits."""
    return [_chip("time_steps", "Time steps", "11", "timeSteps")]


def _circuit_fields() -> list[dict[str, object]]:
    """Return the product-formula fields a Trotter card edits."""
    return [
        *_qutip_fields(),
        _chip("num_steps", "Product steps", "4", "numSteps"),
        _chip("trotter_depth", "Trotter depth", "1", "trotterDepth"),
        _chip("order", "Order", "1", choices=["1", "2"]),
        _chip("seed", "Seed", "0"),
    ]


def _page_caps() -> dict[str, Any]:
    """Return the limit fields the builder copies out of ``_page_limits``."""
    payload = _page_limits()
    states = payload["states"]
    assert isinstance(states, dict)
    return {
        "stateLimits": states,
        "maxOperatorQubits": payload["operatorQubits"],
        "maxTimeSteps": payload["timeSteps"],
        "maxNumSteps": payload["numSteps"],
        "maxTrotterDepth": payload["trotterDepth"],
        "maxShots": payload["shots"],
    }


def _qutip_page() -> dict[str, Any]:
    """Return a complete QuTiP selection with no backend."""
    return {
        "lanes": _LANES,
        "blocks": {
            "state": listed_states(),
            "model": [],
            "simulator": [
                {"id": "qutip", "title": "QuTiP", "observables": True, "setup": _QUTIP_SETUP, "fields": _qutip_fields()}
            ],
            "backend": [
                {
                    "id": "aer",
                    "phrase": "Aer",
                    "shots": True,
                    "setup": "circuit_backend = AerCircuitBackend(shots={shots})",
                }
            ],
            "measure": listed_measurements(),
            "then": listed_actions(),
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
        "stateText": {"basis": "00"},
        "placedSims": [{"id": "qutip", "params": {"time_steps": "11"}}],
        "placedThens": ["plot"],
        "actionText": {"save": "results/run1", "export": "results"},
        "expressionText": {},
        "measureSites": None,
        "shots": "256",
        "qubitsSource": None,
        **_page_caps(),
    }


def _circuit_page() -> dict[str, Any]:
    """Return a complete circuit selection, including a backend."""
    page = _qutip_page()
    page["blocks"]["simulator"] = [
        {
            "id": "trotterization",
            "title": "Trotterization",
            "observables": False,
            "setup": _circuit_setup("TrotterizationSimulator"),
            "fields": _circuit_fields(),
        }
    ]
    page["selection"]["simulator"] = "trotterization"
    page["placedSims"] = [
        {
            "id": "trotterization",
            "params": {
                "time_steps": "11",
                "num_steps": "4",
                "trotter_depth": "1",
                "seed": "0",
                "order": "1",
            },
            "backend": "aer",
            "shots": "256",
        }
    ]
    return page


def _counts_page(expression: str = 'counts["01"] / shots') -> dict[str, Any]:
    """Return a circuit page that measures ``expression``."""
    page = _circuit_page()
    page["blocks"]["measure"].append({"id": "counts", "title": "Counts", "phrase": "Counts on all qubits"})
    page["selection"]["measure"] = "counts"
    page["expressionText"] = {"counts": expression}
    return page


@pytest.mark.qiskit
def test_counts_preview_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qiskit_aer")
    page = _counts_page('counts["00"] / shots')
    page["placedThens"] = ["save"]
    page["selection"]["then"] = "save"
    text = _call("previewText", page)
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, Any] = {}
    exec(compile(text, "preview", "exec"), namespace)
    result = namespace["result"]
    assert result.metadata["measurements"][0]["expression"] == 'counts["00"] / shots'
    assert result.observables[0][0] == 1.0
    assert (tmp_path / "results" / "run1" / "counts.json").is_file()


@pytest.mark.qiskit
def test_expectation_preview_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qiskit_aer")
    page = _circuit_page()
    page["settings"]["total"] = "0.1"
    page["placedSims"][0]["params"]["time_steps"] = "2"
    page["placedSims"][0]["params"]["num_steps"] = "1"
    page["placedSims"][0]["shots"] = "32"
    page["placedThens"] = ["save"]
    page["selection"]["then"] = "save"
    text = _call("previewText", page)
    assert isinstance(text, str)
    assert "Measurement.expectation" not in text
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, Any] = {}
    exec(compile(text, "preview", "exec"), namespace)
    result = namespace["result"]
    assert result.metadata["measurements"] == [
        {
            "qubits": [0],
            "expression": '(counts["0"] - counts["1"]) / shots',
            "label": "expectation on 0",
        },
        {
            "qubits": [1],
            "expression": '(counts["0"] - counts["1"]) / shots',
            "label": "expectation on 1",
        },
    ]
    assert len(result.observables) == 2
