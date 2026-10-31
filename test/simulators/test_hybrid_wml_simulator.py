"""Tests for hybrid wave-matrix Lindbladization."""

from collections.abc import Callable
from concurrent.futures import Future

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

import shadowsim.backends.aer as aer_backend_module
import shadowsim.simulators._time_points as time_points
import shadowsim.simulators.hybrid_wml_simulator as hybrid_module
from shadowsim.core import Hamiltonian, LocalHamiltonian, LocalOperator, Operator, State
from shadowsim.simulators import HybridWMLSimulator, Measurement
from shadowsim.simulators.hybrid_wml_simulator import _hybrid_wml, _hybrid_wml_circuit

Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
LOWERING = np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128)
POPULATION = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=np.complex128)
_MISSING = object()

# Finite-step bias plus shot noise. Checked once with a fixed seed: about 0.04
# for the closed qubit and under 0.01 for amplitude damping.
_CLOSED_TOLERANCE = 0.12
_DAMPING_TOLERANCE = 0.10


def _make(*, shots: int = 32, **kwargs: object) -> HybridWMLSimulator:
    backend = kwargs.get("circuit_backend", _MISSING)
    if backend is _MISSING:
        kwargs["circuit_backend"] = aer_backend_module.AerCircuitBackend(shots=shots)
    elif backend is not None and hasattr(backend, "shots"):
        backend.shots = shots  # type: ignore[attr-defined]
    defaults: dict[str, object] = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.2,
        "time_steps": 2,
        "num_steps": 2,
        "seed": 0,
    }
    defaults.update(kwargs)
    return HybridWMLSimulator(**defaults)  # type: ignore[arg-type]


def _instruction_signature(circuit: object) -> list[tuple[str, tuple[int, ...], tuple[bytes, ...]]]:
    """Return gate names, qubit indexes, and parameter bytes, ignoring register names."""
    rows: list[tuple[str, tuple[int, ...], tuple[bytes, ...]]] = []
    for instruction in circuit.data:  # type: ignore[attr-defined]
        qubits = tuple(int(circuit.find_bit(qubit).index) for qubit in instruction.qubits)  # type: ignore[attr-defined]
        params = tuple(np.asarray(param).tobytes() for param in instruction.operation.params)
        rows.append((instruction.operation.name, qubits, params))
    return rows


def test_run_settings_are_keyword_only() -> None:
    hamiltonians = [LocalHamiltonian(Z, [0])]
    state = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    with pytest.raises(TypeError, match="positional"):
        HybridWMLSimulator(hamiltonians, [], state, 1)  # type: ignore[misc]
    with pytest.raises(TypeError, match="positional"):
        HybridWMLSimulator(hamiltonians, [], state, 1, 0.2, 2, 2)  # type: ignore[misc]

    simulator = _make()
    assert simulator.id == "hybrid_wml_simulator"
    assert simulator.requires_sampling_backend is True
    assert simulator.num_steps == 2
    assert simulator.basis == "Z"


def test_omitted_backend_is_aer() -> None:
    simulator = HybridWMLSimulator(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.1,
        time_steps=2,
        num_steps=1,
    )
    assert isinstance(simulator.circuit_backend, aer_backend_module.AerCircuitBackend)
    assert simulator.seed is None
    assert simulator.basis == "Z"


def test_rejects_non_local_operators() -> None:
    with pytest.raises(TypeError, match="LocalHamiltonian"):
        _make(hamiltonians=[Hamiltonian(Z)])
    with pytest.raises(TypeError, match="LocalOperator"):
        _make(lindblads=[Operator(Z)])


def test_rejects_operators_off_the_register() -> None:
    qutrit = np.eye(3, dtype=np.complex128)
    with pytest.raises(ValueError, match="local_dim must be 2"):
        _make(hamiltonians=[LocalHamiltonian(qutrit, [0], local_dim=3)])
    with pytest.raises(ValueError, match=r"sites \[-1\]"):
        _make(hamiltonians=[LocalHamiltonian(Z, [-1])])
    with pytest.raises(ValueError, match=r"sites \[1\]"):
        _make(hamiltonians=[LocalHamiltonian(Z, [1])])
    with pytest.raises(ValueError, match="local_dim must be 2"):
        _make(lindblads=[LocalOperator(qutrit, [0], local_dim=3)])
    with pytest.raises(ValueError, match=r"sites \[4\]"):
        _make(lindblads=[LocalOperator(Z, [4])])


def test_rejects_a_zero_sampling_weight() -> None:
    zero = np.zeros((2, 2), dtype=np.complex128)
    with pytest.raises(ValueError, match="nonzero"):
        _make(hamiltonians=[LocalHamiltonian(zero, [0])], lindblads=[])
    with pytest.raises(ValueError, match="nonzero"):
        _make(hamiltonians=[LocalHamiltonian(zero, [0])], lindblads=[LocalOperator(zero, [0])])


@pytest.mark.parametrize(
    ("kwargs", "exc", "match"),
    [
        ({"workers": 0}, ValueError, "workers must be a positive integer"),
        ({"workers": -2}, ValueError, "workers must be a positive integer"),
        ({"workers": True}, TypeError, "workers must be an int"),
        ({"workers": 1.5}, TypeError, "workers must be an int"),
        ({"num_steps": 0}, ValueError, "num_steps must be a positive integer"),
        ({"num_steps": -3}, ValueError, "num_steps must be a positive integer"),
        ({"num_steps": True}, TypeError, "num_steps must be an int"),
        ({"num_steps": 1.5}, TypeError, "num_steps must be an int"),
        ({"seed": True}, TypeError, "seed must be an int or None"),
        ({"seed": 1.5}, TypeError, "seed must be an int or None"),
        ({"total_time": -0.1}, ValueError, "total_time must be non-negative"),
        ({"basis": "Q"}, ValueError, "basis must be 1 letters from X, Y, and Z"),
        ({"basis": "XX"}, ValueError, "basis must be 1 letters from X, Y, and Z"),
    ],
)
def test_rejects_bad_run_settings(kwargs: dict[str, object], exc: type[Exception], match: str) -> None:
    with pytest.raises(exc, match=match):
        _make(**kwargs)


def test_rejects_a_backend_without_a_shot_budget() -> None:
    class Expectations:
        name = "expectations"

    with pytest.raises(ValueError, match="shot budget"):
        _make(circuit_backend=Expectations())
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _make(shots=0)


def test_t0_counts_are_the_initial_computational_state() -> None:
    shots = 32
    one = _make(
        initial_state=State(np.array([0.0, 1.0], dtype=np.complex128), 1),
        total_time=1.0,
        time_steps=1,
        num_steps=3,
        shots=shots,
        seed=4,
    )
    one_result = one.simulate()
    assert one_result.counts == [{"1": shots}]
    assert one_result.observables == []
    assert one_result.metadata["shots"] == shots
    assert one_result.metadata["num_steps"] == 3
    assert one_result.metadata["basis"] == "Z"
    assert one_result.metadata["lindblad_count"] == 0
    assert one_result.metadata["circuit_backend"] == "aer"

    # Kronecker order: qubit 0 is the most significant bit, so index 2 is |10>.
    excited = np.zeros(4, dtype=np.complex128)
    excited[2] = 1.0
    two = _make(
        initial_state=State(excited, 2),
        num_qubits=2,
        total_time=1.0,
        time_steps=1,
        num_steps=3,
        shots=shots,
        seed=4,
    )
    assert two.simulate().counts == [{"10": shots}]


def test_x_basis_reads_the_plus_state_as_zero() -> None:
    plus = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2.0)
    shots = 32
    simulator = _make(
        initial_state=State(plus, 1),
        basis="X",
        total_time=0.0,
        time_steps=1,
        num_steps=1,
        shots=shots,
    )
    assert simulator.basis == "X"
    assert simulator.simulate().counts == [{"0": shots}]


def test_t0_with_only_a_lindblad_stays_in_the_initial_state() -> None:
    shots = 16
    zero = np.zeros((2, 2), dtype=np.complex128)
    state = State(np.array([0.0, 1.0], dtype=np.complex128), 1)
    simulator = _make(
        hamiltonians=[LocalHamiltonian(zero, [0])],
        lindblads=[LocalOperator(LOWERING, [0])],
        initial_state=state,
        total_time=0.0,
        time_steps=2,
        num_steps=3,
        shots=shots,
        seed=1,
    )
    assert simulator.simulate().counts == [{"1": shots}, {"1": shots}]

    circuit = _hybrid_wml_circuit([], [LocalOperator(LOWERING, [0])], state, 1, t=0.0, num_steps=1)
    assert [register.name for register in circuit.qregs] == ["ancilla", "system"]


def test_a_seed_repeats_the_same_counts() -> None:
    settings: dict[str, object] = {
        "shots": 24,
        "num_steps": 4,
        "time_steps": 3,
        "total_time": 0.5,
        "seed": 11,
    }
    first = _make(**settings).simulate().counts
    second = _make(**settings).simulate().counts
    assert first == second
    assert first is not None
    assert len(first) == 3


def test_workers_match_the_serial_counts() -> None:
    settings: dict[str, object] = {
        "shots": 8,
        "num_steps": 2,
        "time_steps": 2,
        "total_time": 0.3,
        "seed": -4,
    }
    serial = _make(workers=1, **settings).simulate().counts
    parallel = _make(workers=2, **settings).simulate().counts
    assert serial == parallel
    assert serial is not None
    assert len(serial) == 2


def test_serial_run_is_quiet_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(hybrid_module, "_hybrid_wml", lambda *args, **kwargs: {"0": 4})

    _make().simulate()

    assert capsys.readouterr().out == ""


def test_serial_run_reports_progress_when_verbose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hybrid_module, "_hybrid_wml", lambda *args, **kwargs: {"0": 4})
    seen: list[tuple[int, int]] = []

    _make(verbose=True, progress=lambda step, total: seen.append((step, total))).simulate()

    output = capsys.readouterr().out
    assert "Working on time step 0.0" in output
    assert "Working on time step 0.2" in output
    assert seen == [(0, 2), (1, 2)]


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
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        return None


def test_parallel_run_reports_progress_and_keeps_system_bits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake(*args: object, **kwargs: object) -> dict[str, int]:
        if float(args[4]) == 0.0:  # type: ignore[arg-type]
            return {"01": 4}
        return {"10": 4}

    monkeypatch.setattr(hybrid_module, "_hybrid_wml", fake)
    monkeypatch.setattr(time_points, "ProcessPoolExecutor", _RunSubmitted)
    seen: list[tuple[int, int]] = []
    simulator = _make(workers=2, verbose=True, seed=-4, progress=lambda step, total: seen.append((step, total)))

    result = simulator.simulate()

    assert result.counts == [{"10": 4}, {"01": 4}]
    assert sorted(seen) == [(0, 2), (1, 2)]
    output = capsys.readouterr().out
    assert "Working on time step 0.0" in output
    assert "Working on time step 0.2" in output


def test_metrics_circuit_matches_the_final_executed_circuit() -> None:
    class Recording:
        name = "recording"
        shots = 1

        def __init__(self) -> None:
            self.circuit = None
            self.seeds: list[int | None] = []

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots
            self.circuit = circuit
            self.seeds.append(seed)
            return {"0": 1}

    backend = Recording()
    simulator = _make(
        circuit_backend=backend,
        shots=1,
        time_steps=3,
        total_time=0.4,
        num_steps=2,
        seed=9,
        basis="X",
    )
    simulator.simulate()

    assert _instruction_signature(simulator.metrics_circuit()) == _instruction_signature(backend.circuit)
    assert len(set(backend.seeds)) == 3


def test_str_and_repr() -> None:
    simulator = _make(shots=42, seed=7, num_steps=5)
    text = str(simulator)
    rep = repr(simulator)
    assert "HybridWMLSimulator(" in text
    assert "shots=42" in text
    assert "num_steps=5" in text
    assert "seed=7" in text
    assert "HybridWMLSimulator(" in rep
    assert "workers=1" in rep
    assert "seed=7" in rep
    assert "progress=" in rep


def test_hybrid_wml_rejects_bad_shots_seed_time_and_steps() -> None:
    state = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    hamiltonians = [LocalHamiltonian(Z, [0])]
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _hybrid_wml(hamiltonians, [], state, 1, 0.0, 1, shots=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _hybrid_wml(hamiltonians, [], state, 1, 0.0, 1, shots=1.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _hybrid_wml(hamiltonians, [], state, 1, 0.0, 1, shots=0)
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _hybrid_wml(hamiltonians, [], state, 1, 0.0, 1, shots=1, seed=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="t must be non-negative"):
        _hybrid_wml_circuit(hamiltonians, [], state, 1, t=-1.0, num_steps=1)
    with pytest.raises(ValueError, match="num_steps must be a positive integer"):
        _hybrid_wml_circuit(hamiltonians, [], state, 1, t=0.0, num_steps=0)
    with pytest.raises(TypeError, match="num_steps must be an int"):
        _hybrid_wml_circuit(hamiltonians, [], state, 1, t=0.0, num_steps=1.5)  # type: ignore[arg-type]


def test_hybrid_wml_defaults_to_aer_and_forwards_an_unseeded_run() -> None:
    counts = _hybrid_wml(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        0.0,
        1,
        shots=1,
        seed=None,
    )
    assert counts == {"0": 1}


def test_unseeded_run_passes_no_simulator_seed() -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.seed: int | None = 0

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del circuit, shots
            self.seed = seed
            return {"0": 1}

    backend = Recording()
    _hybrid_wml(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        0.0,
        1,
        shots=1,
        seed=None,
        circuit_backend=backend,  # type: ignore[arg-type]
    )
    assert backend.seed is None


def test_verbose_circuit_prints_every_tenth_step(capsys: pytest.CaptureFixture[str]) -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"00": 1}

    backend = Recording()
    zz = np.diag([1.0, -1.0, -1.0, 1.0]).astype(np.complex128)
    ground = np.diag([1.0, 0.0]).astype(np.complex128)
    _hybrid_wml(
        [
            LocalHamiltonian(Z, [0]),
            LocalHamiltonian(zz, [0, 1]),
            LocalHamiltonian(ground, [1]),
        ],
        [
            LocalOperator(np.zeros((2, 2), dtype=np.complex128), [0]),
            LocalOperator(LOWERING, [1]),
        ],
        State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2),
        2,
        0.2,
        11,
        verbose=True,
        shots=1,
        seed=1,
        circuit_backend=backend,  # type: ignore[arg-type]
    )

    output = capsys.readouterr().out
    assert "Working on iteration 0 out of 11" in output
    assert "Working on iteration 10 out of 11" in output
    assert "Working on iteration 1 out of 11" not in output
    assert backend.circuit is not None
    sizes = {
        np.asarray(instruction.operation.params[0]).shape
        for instruction in backend.circuit.data  # type: ignore[attr-defined]
        if instruction.operation.name == "unitary"
    }
    assert (16, 16) in sizes
    assert (4, 4) in sizes


@pytest.mark.cross_extra
def test_closed_one_qubit_agrees_with_qutip() -> None:
    pytest.importorskip("qutip")
    from shadowsim.benchmarking import Benchmark
    from shadowsim.simulators import QutipSimulator

    state = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    total_time = float(np.pi / 2)
    qutip = QutipSimulator(
        [LocalHamiltonian(X, [0])],
        [],
        state,
        [Operator(POPULATION)],
        num_qubits=1,
        total_time=total_time,
        time_steps=2,
    )
    hybrid = _make(
        hamiltonians=[LocalHamiltonian(X, [0])],
        initial_state=state,
        total_time=total_time,
        time_steps=2,
        num_steps=40,
        shots=800,
        seed=2,
    )
    benchmark = Benchmark(qutip, hybrid)
    benchmark.run()
    hybrid.measure([Measurement.population(0)])

    metrics = benchmark.error_metrics()
    assert metrics[0]["observables"][0]["linf"] < _CLOSED_TOLERANCE


@pytest.mark.cross_extra
def test_amplitude_damping_agrees_with_qutip() -> None:
    pytest.importorskip("qutip")
    from shadowsim.benchmarking import Benchmark
    from shadowsim.simulators import QutipSimulator

    zero = np.zeros((2, 2), dtype=np.complex128)
    state = State(np.array([0.0, 1.0], dtype=np.complex128), 1)
    hamiltonians = [LocalHamiltonian(zero, [0])]
    lindblads = [LocalOperator(LOWERING, [0])]
    qutip = QutipSimulator(
        hamiltonians,
        lindblads,
        state,
        [Operator(POPULATION)],
        num_qubits=1,
        total_time=1.0,
        time_steps=3,
    )
    hybrid = _make(
        hamiltonians=hamiltonians,
        lindblads=lindblads,
        initial_state=state,
        total_time=1.0,
        time_steps=3,
        num_steps=40,
        shots=800,
        seed=3,
    )
    benchmark = Benchmark(qutip, hybrid)
    benchmark.run()
    hybrid.measure([Measurement.population(0)])

    metrics = benchmark.error_metrics()
    assert metrics[0]["observables"][0]["linf"] < _DAMPING_TOLERANCE
