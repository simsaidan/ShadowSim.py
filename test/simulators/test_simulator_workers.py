"""Concurrency tests for the Aer simulators."""

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from types import ModuleType

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

import shadowsim.simulators._time_points as time_points
import shadowsim.simulators.splitjmatrix_simulator as splitj_module
import shadowsim.simulators.trotterization_simulator as trotter_module
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import SplitJMatrixSimulator, TrotterizationSimulator

X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_TOTAL_TIME = float(np.pi / 2)


def _settings(**kwargs: object) -> dict[str, object]:
    settings: dict[str, object] = {
        "hamiltonians": [LocalHamiltonian(X, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": _TOTAL_TIME,
        "time_steps": 2,
        "num_steps": 1,
        "shots": 16,
        "seed": 5,
    }
    settings.update(kwargs)
    return settings


def _make_split(**kwargs: object) -> SplitJMatrixSimulator:
    return SplitJMatrixSimulator(**_settings(**kwargs))


def _make_split_system(**kwargs: object) -> SplitJMatrixSimulator:
    """Measure the system qubit. Split J's ancilla occupies bit 0."""
    kwargs.setdefault("measurement_groups", [1])
    return _make_split(**kwargs)


def _make_trotter(**kwargs: object) -> TrotterizationSimulator:
    return TrotterizationSimulator(**_settings(**kwargs))


_Make = Callable[..., SplitJMatrixSimulator | TrotterizationSimulator]
_SIMULATORS = [
    pytest.param(_make_split, id="split_j"),
    pytest.param(_make_trotter, id="trotter"),
]
_REAL_SIMULATORS = [
    pytest.param(_make_split_system, id="split_j"),
    pytest.param(_make_trotter, id="trotter"),
]


def _counts_for_time(args: tuple[object, ...], time_index: int, *, later: float) -> dict[str, int]:
    """Return a sure ``|0>`` or ``|1>`` count, so a swapped time is visible."""
    t = float(args[time_index])  # type: ignore[arg-type]
    if np.isclose(t, later):
        return {"1": 4}
    return {"0": 4}


class _LastFinishesFirst:
    """Finish the later submission before ``as_completed`` sees the earlier one."""

    def __init__(self, max_workers: int, mp_context: object | None = None) -> None:
        self.max_workers = max_workers
        self.mp_context = mp_context
        self._jobs: list[tuple[Future[dict[str, int]], Callable[..., dict[str, int]], tuple[object, ...]]] = []
        self._thread: threading.Thread | None = None

    def submit(
        self,
        fn: Callable[..., dict[str, int]],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[dict[str, int]]:
        future: Future[dict[str, int]] = Future()
        self._jobs.append((future, fn, args))
        if len(self._jobs) >= 2:
            self._finish(self._jobs[-1])
            self._thread = threading.Thread(target=self._finish_earlier, daemon=True)
            self._thread.start()
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        if wait and self._thread is not None:
            self._thread.join(timeout=2)

    def _finish(self, job: tuple[Future[dict[str, int]], Callable[..., dict[str, int]], tuple[object, ...]]) -> None:
        future, fn, args = job
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)

    def _finish_earlier(self) -> None:
        first = self._jobs[0][0]
        deadline = time.monotonic() + 2
        # Wait until as_completed has installed its waiter, so this future is
        # still pending in that snapshot and completes afterwards.
        while not first._waiters:  # type: ignore[attr-defined]
            if time.monotonic() > deadline:
                first.set_exception(TimeoutError("as_completed did not start waiting"))
                return
            time.sleep(0.001)
        for job in reversed(self._jobs[:-1]):
            self._finish(job)


class _RunSubmitted:
    """Run each submission in this process and store its outcome on the future."""

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
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        return None


@pytest.mark.parametrize("make", _REAL_SIMULATORS)
def test_workers_match_the_serial_trace(make: _Make) -> None:
    serial = make(workers=1).simulate()
    parallel = make(workers=2).simulate()

    assert len(serial.observables[0]) >= 2
    assert not np.isclose(serial.observables[0][0], serial.observables[0][1])
    for left, right in zip(serial.observables, parallel.observables, strict=True):
        assert np.array_equal(left, right)


@pytest.mark.parametrize(
    ("make", "module", "circuit_name", "time_index"),
    [
        pytest.param(_make_split, splitj_module, "_split_jmatrix", 4, id="split_j"),
        pytest.param(_make_trotter, trotter_module, "_trotter_circuit_counts", 3, id="trotter"),
    ],
)
def test_out_of_order_completion_keeps_tlist_order(
    make: _Make,
    module: ModuleType,
    circuit_name: str,
    time_index: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[int, int]] = []
    sim = make(workers=2, progress=lambda step, total: seen.append((step, total)))
    later = float(sim.tlist[-1])

    def fake_counts(*args: object, **kwargs: object) -> dict[str, int]:
        return _counts_for_time(args, time_index, later=later)

    monkeypatch.setattr(module, circuit_name, fake_counts)
    monkeypatch.setattr(time_points, "ProcessPoolExecutor", _LastFinishesFirst)

    result = sim.simulate()

    assert np.array_equal(result.observables[0], [0.0, 1.0])
    assert seen == [(1, 2), (0, 2)]


@pytest.mark.parametrize("make", _SIMULATORS)
def test_workers_below_one_are_rejected(make: _Make) -> None:
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        make(workers=0)


@pytest.mark.parametrize(
    ("make", "module", "circuit_name", "time_index"),
    [
        pytest.param(_make_split, splitj_module, "_split_jmatrix", 4, id="split_j"),
        pytest.param(_make_trotter, trotter_module, "_trotter_circuit_counts", 3, id="trotter"),
    ],
)
def test_a_failed_time_point_does_not_return_partial_results(
    make: _Make,
    module: ModuleType,
    circuit_name: str,
    time_index: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sim = make(workers=2)
    later = float(sim.tlist[-1])

    def fake_counts(*args: object, **kwargs: object) -> dict[str, int]:
        if np.isclose(float(args[time_index]), later):  # type: ignore[arg-type]
            raise RuntimeError("time point failed")
        return {"0": 4}

    monkeypatch.setattr(module, circuit_name, fake_counts)
    monkeypatch.setattr(time_points, "ProcessPoolExecutor", _RunSubmitted)

    with pytest.raises(RuntimeError, match="time point failed"):
        sim.simulate()

    assert sim.results is None
    assert sim.last_result is None
