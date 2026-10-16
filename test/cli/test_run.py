"""Tests for building a QuTiP simulator from a builder-page selection."""

import builtins
import importlib
import json
import threading
import types
import urllib.error
import urllib.request
from collections.abc import Mapping
from http.server import HTTPServer
from typing import Protocol

import pytest

from shadowsim.backends import listed_backends
from shadowsim.cli.run import _initial_state, build_simulator
from shadowsim.cli.serve import _Handler
from shadowsim.models.catalog import _describe_models, listed_model_terms, listed_models
from shadowsim.simulators.catalog import _describe_simulator, listed_simulators


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
        ({"simulator": "splitjmatrix"}, "only QuTiP"),
        ({"simulator": "trotterization"}, "only QuTiP"),
        ({"backend": "qiskit"}, "Qiskit backend"),
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
        ({"simulator": None}, "only QuTiP"),
        ({"state": "nope"}, "unknown initial state"),
        ({"model": "nope"}, "unknown model"),
        ({"measure": "nope"}, "unknown measurement"),
    ],
)
def test_build_simulator_rejects(overrides: dict[str, object], message: str, forbid_qutip: None) -> None:
    with pytest.raises(ValueError, match=message):
        build_simulator(_selection(**overrides))


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
    simulator = build_simulator(_selection(**overrides), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
def test_tavis_cummings_ignores_the_qubits_field() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(model="tavis_cummings", qubits="1", basis="100"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


@pytest.mark.qutip
def test_jaynes_cummings_ignores_the_qubits_field() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(model="jaynes_cummings", qubits="1", basis="100"), time_steps=2)
    assert simulator.num_qubits == 3
    assert simulator.initial_state.get_num_qubits() == 3


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


def test_one_qubit_encodings_prepare_that_size() -> None:
    assert _initial_state("angle", 1).get_num_qubits() == 1
    assert _initial_state("amplitude", 1).get_num_qubits() == 1


def test_initial_state_rejects_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown initial state"):
        _initial_state("nope", 2)


@pytest.mark.qutip
def test_pauli_measurement_records_one_curve_per_qubit() -> None:
    pytest.importorskip("qutip")
    simulator = build_simulator(_selection(measure="x"), time_steps=2)
    assert len(simulator.observables) == 2


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


def _request(method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method)
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
    status, body = _post(json.dumps(_selection(simulator="splitjmatrix")).encode())
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


def test_listed_backends_reads_concrete_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("shadowsim.backends.circuit")

    class CircuitBackend(Protocol):
        def run_counts(self) -> None: ...

    class AerCircuitBackend:
        """Run a circuit on Qiskit Aer and return shot counts."""

        def __init__(self) -> None:
            return None

        def run_counts(self) -> None:
            return None

    class QiskitCircuitBackend:
        """Run a circuit on a caller-supplied Qiskit ``BackendV2``.

        The wrapped backend receives ``run``.
        """

        def __init__(self, backend: object, *, name: str = "qiskit") -> None:
            del backend, name

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

    BareCircuitBackend.__doc__ = None
    for cls in (CircuitBackend, AerCircuitBackend, QiskitCircuitBackend, BareCircuitBackend, NoteCircuitBackend):
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
        assert name == "shadowsim.backends.circuit"
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
        },
        {
            "id": "qiskit",
            "title": "Qiskit",
            "detail": "Run a circuit on a caller-supplied Qiskit BackendV2.",
            "phrase": "Qiskit",
            "setup": "circuit_backend = QiskitCircuitBackend(backend)",
        },
        {
            "id": "bare",
            "title": "Bare",
            "detail": "Bare",
            "phrase": "Bare",
            "setup": "circuit_backend = BareCircuitBackend()",
        },
    ]


@pytest.mark.qiskit
def test_listed_backends_matches_the_circuit_module() -> None:
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")
    listed = listed_backends()
    assert [item["id"] for item in listed] == ["aer", "qiskit"]
    assert listed[0]["setup"] == "circuit_backend = AerCircuitBackend()"
    assert listed[1]["setup"] == "circuit_backend = QiskitCircuitBackend(backend)"
    assert "Aer" in listed[0]["detail"]
    assert "BackendV2" in listed[1]["detail"]


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
        },
        {
            "id": "odd",
            "title": "Odd",
            "detail": "Odd model.",
            "phrase": "Odd",
            "setup": "model = odd(edges)",
            "qubits": False,
        },
        {
            "id": "bare",
            "title": "Bare",
            "detail": "Bare",
            "phrase": "Bare",
            "setup": "model = bare()",
            "qubits": False,
        },
    ]


def test_listed_models_reads_the_package_factories() -> None:
    listed = listed_models()
    assert [item["id"] for item in listed] == ["ising", "jaynes_cummings", "tavis_cummings"]
    assert listed[0]["title"] == "Ising"
    assert listed[0]["qubits"] is True
    assert listed[0]["setup"] == "model = ising(n_qubits={qubits})"
    assert listed[1]["title"] == "Jaynes-Cummings"
    assert listed[1]["qubits"] is False
    assert listed[2]["setup"] == "model = tavis_cummings()"


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
    assert "BareSimulator" in listed[0]["setup"]
    assert listed[1]["detail"] == "Simulate with a note."
    assert listed[1]["observables"] is True


def test_describe_simulator_uses_the_title_without_a_docstring(monkeypatch: pytest.MonkeyPatch) -> None:
    class BareSimulator:
        def __init__(self) -> None:
            return None

    monkeypatch.setattr("shadowsim.simulators.catalog.inspect.getdoc", lambda cls: None)
    described = _describe_simulator(BareSimulator)
    assert described["detail"] == "Bare"
    assert described["observables"] is False


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
    assert listed[0]["setup"].startswith("{name} = QutipSimulator")
    assert "{total}" in listed[0]["setup"]
    assert listed[1]["observables"] is False
    assert "SplitJMatrixSimulator" in listed[1]["setup"]
    assert "QuTiP" in listed[0]["detail"]


def test_get_models_returns_the_package_factories() -> None:
    status, body = _request("GET", "/models")
    payload = json.loads(body)
    assert status == 200
    assert [item["id"] for item in payload["models"]] == [
        "ising",
        "jaynes_cummings",
        "tavis_cummings",
        "hamiltonian",
        "local_hamiltonian",
        "lindblad",
    ]


def test_get_simulators_reports_an_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> list[object]:
        raise ImportError("no simulators could be imported")

    monkeypatch.setattr("shadowsim.cli.serve.listed_simulators", explode)
    status, body = _request("GET", "/simulators")
    payload = json.loads(body)
    assert status == 500
    assert "no simulators" in payload["error"]


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


def test_get_backends_reports_an_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> list[object]:
        raise ImportError("shadowsim.backends.circuit requires the qiskit extra")

    monkeypatch.setattr("shadowsim.cli.serve.listed_backends", explode)
    status, body = _request("GET", "/backends")
    payload = json.loads(body)
    assert status == 500
    assert "qiskit extra" in payload["error"]


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
