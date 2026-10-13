"""Tests for ``Simulator.start()`` and ``SimulationJob``."""

import importlib
import threading
from collections.abc import Callable
from concurrent.futures import Future
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

import shadowsim.simulators._time_points as time_points
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, State
from shadowsim.simulators import SimulationJob, SimulationStatus, Simulator
from shadowsim.simulators.result import SimulationResult

Z = np.diag([1.0, -1.0]).astype(np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_STATE = State(np.array([1.0, 0.0], dtype=np.complex128), 1)


def _new(cls: type[Simulator], sim_id: str, *, time_steps: int = 3) -> Simulator:
    return cls(
        [Hamiltonian(Z)],
        [],
        _STATE,
        num_qubits=1,
        total_time=1.0,
        time_steps=time_steps,
        id=sim_id,
    )


def _curve(sim: Simulator) -> SimulationResult:
    return sim._make_result([np.linspace(0.0, 1.0, sim.time_steps)])


def _assert_same_result(left: SimulationResult, right: SimulationResult) -> None:
    assert np.array_equal(left.times, right.times)
    assert left.seed == right.seed
    assert left.algorithm == right.algorithm
    assert left.runtime == right.runtime
    assert left.states == right.states
    assert left.metadata == right.metadata
    assert len(left.observables) == len(right.observables)
    for actual, expected in zip(left.observables, right.observables, strict=True):
        assert np.array_equal(actual, expected)


def test_start_returns_while_simulate_is_running() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Blocking(Simulator):
        def simulate(self) -> SimulationResult:
            entered.set()
            if not release.wait(timeout=2):
                raise TimeoutError("release was not set")
            return _curve(self)

    class Direct(Simulator):
        def simulate(self) -> SimulationResult:
            return _curve(self)

    sim = _new(Blocking, "blocking")
    try:
        job = sim.start()
        assert isinstance(job, SimulationJob)
        assert entered.wait(timeout=2)
        assert job.status is SimulationStatus.RUNNING
        with pytest.raises(TimeoutError, match="still running"):
            job.result(timeout=0)
        release.set()
        result = job.result(timeout=2)
    finally:
        release.set()

    assert job.status is SimulationStatus.SUCCEEDED
    assert result is job.result()
    _assert_same_result(result, _new(Direct, "blocking").simulate())


def test_failed_job_raises_the_simulate_exception() -> None:
    class Boom(Simulator):
        def simulate(self) -> SimulationResult:
            raise ValueError("boom")

    job = _new(Boom, "boom").start()
    with pytest.raises(ValueError, match="boom") as first:
        job.result(timeout=2)
    with pytest.raises(ValueError, match="boom") as second:
        job.result()
    assert first.value is second.value
    assert job.status is SimulationStatus.FAILED


def test_second_start_while_running_raises() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Blocking(Simulator):
        def simulate(self) -> SimulationResult:
            entered.set()
            if not release.wait(timeout=2):
                raise TimeoutError("release was not set")
            return _curve(self)

    sim = _new(Blocking, "blocking")
    try:
        job = sim.start()
        assert entered.wait(timeout=2)
        with pytest.raises(RuntimeError, match="already running"):
            sim.start()
        release.set()
        result = job.result(timeout=2)
    finally:
        release.set()

    assert job.status is SimulationStatus.SUCCEEDED
    assert np.array_equal(result.observables[0], np.linspace(0.0, 1.0, sim.time_steps))


def _require_qiskit() -> None:
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")
    pytest.importorskip("scipy")


def _load_backend(name: str) -> tuple[ModuleType, str, Callable[..., Simulator]]:
    if name == "split_j":
        module = importlib.import_module("shadowsim.simulators.splitjmatrix_simulator")
        return module, "_split_jmatrix", module.SplitJMatrixSimulator
    module = importlib.import_module("shadowsim.simulators.trotterization_simulator")
    return module, "_trotter_circuit_counts", module.TrotterizationSimulator


def _aer_settings(**kwargs: object) -> dict[str, object]:
    settings: dict[str, object] = {
        "hamiltonians": [LocalHamiltonian(X, [0])],
        "lindblads": [],
        "initial_state": _STATE,
        "num_qubits": 1,
        "total_time": 1.0,
        "time_steps": 2,
        "num_steps": 1,
        "shots": 16,
        "seed": 5,
    }
    settings.update(kwargs)
    return settings


class _InlinePool:
    """Run pool submissions in this process so a stubbed circuit stays patched."""

    def __init__(self, max_workers: int, mp_context: object | None = None) -> None:
        self.max_workers = max_workers
        self.mp_context = mp_context

    def submit(
        self,
        fn: Callable[..., dict[str, int]],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[dict[str, int]]:
        future: Future[dict[str, int]] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        return None


@pytest.mark.qiskit
@pytest.mark.parametrize("backend", ["split_j", "trotter"])
def test_aer_job_counts_steps_before_success(monkeypatch: pytest.MonkeyPatch, backend: str) -> None:
    _require_qiskit()
    module, circuit_name, cls = _load_backend(backend)
    release = threading.Event()
    in_second = threading.Event()
    calls = {"n": 0}

    def fake(*args: object, **kwargs: object) -> dict[str, int]:
        calls["n"] += 1
        if calls["n"] >= 2:
            in_second.set()
            if not release.wait(timeout=2):
                raise TimeoutError("release was not set")
        return {"0": 10}

    monkeypatch.setattr(module, circuit_name, fake)
    sim = cls(**_aer_settings(workers=1))
    try:
        job = sim.start()
        assert in_second.wait(timeout=2)
        assert job.status is SimulationStatus.RUNNING
        assert job.completed_steps == 1
        assert job.total_steps == sim.time_steps
        release.set()
        job.result(timeout=2)
    finally:
        release.set()

    assert job.status is SimulationStatus.SUCCEEDED
    assert job.completed_steps == sim.time_steps
    assert job.total_steps == sim.time_steps


@pytest.mark.qiskit
@pytest.mark.parametrize("backend", ["split_j", "trotter"])
def test_parallel_job_counts_finished_steps(monkeypatch: pytest.MonkeyPatch, backend: str) -> None:
    _require_qiskit()
    module, circuit_name, cls = _load_backend(backend)
    monkeypatch.setattr(time_points, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(module, circuit_name, lambda *args, **kwargs: {"0": 10})
    sim = cls(**_aer_settings(workers=2))
    job = sim.start()
    job.result(timeout=2)
    assert job.status is SimulationStatus.SUCCEEDED
    assert job.completed_steps == sim.time_steps
    assert job.total_steps == sim.time_steps


@pytest.mark.qutip
def test_qutip_job_leaves_step_counts_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("qutip")
    import shadowsim.simulators.qutip_simulator as qutip_module
    from shadowsim.simulators import QutipSimulator

    entered = threading.Event()
    release = threading.Event()

    def fake_mesolve(*args: object, **kwargs: object) -> SimpleNamespace:
        entered.set()
        if not release.wait(timeout=2):
            raise TimeoutError("release was not set")
        tlist = args[2]
        assert isinstance(tlist, np.ndarray)
        return SimpleNamespace(expect=[np.zeros(tlist.shape[0])])

    monkeypatch.setattr(qutip_module, "mesolve", fake_mesolve)
    sim = QutipSimulator(
        [Hamiltonian(Z)],
        [],
        _STATE,
        [Operator(Z)],
        num_qubits=1,
        total_time=0.1,
        time_steps=3,
    )
    try:
        job = sim.start()
        assert entered.wait(timeout=2)
        assert job.status is SimulationStatus.RUNNING
        assert job.completed_steps is None
        assert job.total_steps is None
        release.set()
        job.result(timeout=2)
    finally:
        release.set()

    assert job.status is SimulationStatus.SUCCEEDED
    assert job.completed_steps is None
    assert job.total_steps is None
