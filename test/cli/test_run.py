"""Tests for building a QuTiP simulator from a builder-page selection."""

import builtins
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping
from http.server import HTTPServer

import pytest

from shadowsim.cli.run import build_simulator
from shadowsim.cli.serve import _Handler


def _selection(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state": "basis",
        "model": "tfim",
        "simulator": "qutip",
        "backend": "aer",
        "then": "save",
        "qubits": "2",
        "total": "0.5",
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
        ({"simulator": "splitj"}, "only QuTiP"),
        ({"simulator": "trotter"}, "only QuTiP"),
        ({"backend": "qiskit"}, "Qiskit backend"),
        ({"backend": "other"}, "only Aer"),
        ({"total": "0"}, "positive number"),
        ({"total": 0}, "positive number"),
        ({"total": "-1"}, "positive number"),
        ({"total": ""}, "positive number"),
        ({"qubits": "1"}, "at least 2"),
        ({"qubits": 1}, "at least 2"),
        ({"qubits": "2.5"}, "integer"),
        ({"qubits": ""}, "integer"),
        ({"state": "nope"}, "unknown initial state"),
        ({"model": "nope"}, "unknown model"),
    ],
)
def test_build_simulator_rejects(overrides: dict[str, object], message: str, forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match=message):
        build_simulator(_selection(**overrides))


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
    simulator = build_simulator(_selection(state=state, qubits="3"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
def test_tavis_cummings_ignores_the_qubits_field() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(model="tavis", qubits="1"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
def test_then_does_not_change_the_simulator() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(then="plot"), time_steps=2)
    assert simulator.id == "qutip_simulator"
    assert simulator.num_qubits == 2


def _post(body: bytes, *, path: str = "/runs") -> tuple[int, bytes]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST")
    try:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    finally:
        thread.join(timeout=60)
        server.server_close()


def test_post_runs_rejects_a_selection() -> None:
    status, body = _post(json.dumps(_selection(simulator="splitj")).encode())
    payload = json.loads(body)
    assert status == 400
    assert "only QuTiP" in payload["error"]


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


def test_post_runs_reports_a_simulator_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(selection: Mapping[str, object], *, time_steps: int = 101) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("shadowsim.cli.serve.build_simulator", explode)
    status, body = _post(json.dumps(_selection()).encode())
    payload = json.loads(body)
    assert status == 500
    assert payload["error"] == "boom"


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
    assert all(len(curve) == 101 for curve in payload["observables"])
    assert "states" not in payload
