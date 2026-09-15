"""Tests for the closed-system TrotterizationSimulator."""

import numpy as np
import pytest

import shadowsim.simulators.trotterization_simulator as trotter_module
from shadowsim.benchmarking import Benchmark
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, State
from shadowsim.simulators import QutipSimulator, TrotterizationSimulator, population_one
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import _trace_qubits, _trotter_circuit_counts

Z = np.diag([1.0, -1.0]).astype(np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
ONE = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=np.complex128)


def _tiny(**kwargs):
    defaults = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.1,
        "time_steps": 3,
        "num_steps": 4,
        "shots": 256,
        "seed": 0,
    }
    defaults.update(kwargs)
    return TrotterizationSimulator(**defaults)


def _fake_aer_backend(monkeypatch, ctor_kwargs_log=None):
    class FakeResult:
        def get_counts(self):
            return {"0": 1}

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeBackend:
        def __init__(self, **kwargs):
            if ctor_kwargs_log is not None:
                ctor_kwargs_log.append(kwargs)

        def run(self, compiled, shots):
            return FakeJob()

    monkeypatch.setattr(trotter_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(trotter_module, "transpile", lambda circ, backend: circ)


def test_trotterization_simulator_is_simulator():
    sim = _tiny()
    assert isinstance(sim, Simulator)
    assert sim.id == "trotterization_simulator"


def test_trotterization_simulator_rejects_lindblads():
    with pytest.raises(ValueError, match="closed-system"):
        _tiny(lindblads=[Operator(Z)])


def test_trotterization_simulator_rejects_non_local_hamiltonian():
    with pytest.raises(TypeError, match="LocalHamiltonian"):
        _tiny(hamiltonians=[Hamiltonian(Z)])


def test_trotterization_simulator_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _tiny(shots=0)


def test_trotterization_simulator_rejects_nonpositive_num_steps():
    with pytest.raises(ValueError, match="num_steps must be a positive integer"):
        _tiny(num_steps=0)


def test_trotterization_simulator_rejects_nonpositive_trotter_depth():
    with pytest.raises(ValueError, match="trotter_depth must be a positive integer"):
        _tiny(trotter_depth=0)


def test_trotterization_simulator_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _tiny(seed=1.5)  # type: ignore[arg-type]


def test_trotterization_simulator_rejects_reducer_length_mismatch():
    with pytest.raises(ValueError, match="reducers and measurement_groups"):
        _tiny(measurement_groups=[0], reducers=[population_one, population_one])


def test_trotterization_simulator_forwards_seed(monkeypatch):
    seen_seeds = []

    def fake_counts(*args, **kwargs):
        seen_seeds.append(kwargs["seed"])
        return {"0": 10}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    _tiny(seed=7, time_steps=2).simulate()

    assert seen_seeds == [7, 7]


def test_trotterization_simulator_progress_callback(monkeypatch):
    seen = []

    def fake_counts(*args, **kwargs):
        return {"0": 10}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    _tiny(time_steps=2, progress=lambda step, total: seen.append((step, total))).simulate()

    assert seen == [(0, 2), (1, 2)]


def test_trotterization_simulator_verbose_prints(monkeypatch, capsys):
    def fake_counts(*args, **kwargs):
        return {"0": 10}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    _tiny(time_steps=2, total_time=1.0, verbose=True).simulate()

    out = capsys.readouterr().out
    assert "Working on time step 0.0" in out
    assert "Working on time step 1.0" in out


def test_trotterization_simulator_grouped_measurement_groups(monkeypatch):
    def fake_counts(*args, **kwargs):
        return {"0": 7, "1": 3}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    results = _tiny(
        time_steps=1,
        measurement_groups=[[0]],
        reducers=[population_one],
    ).simulate()

    assert len(results) == 1
    assert len(results[0]) == 1
    assert results[0][0] == pytest.approx(0.3)


def test_trotterization_simulator_simulate_smoke():
    sim = _tiny()
    results = sim.simulate()
    assert len(results) == 1
    assert len(results[0]) == 3
    assert all(0.0 <= x <= 1.0 for x in results[0])


def test_trotterization_simulator_seed_reproducible():
    a = _tiny(seed=11).simulate()
    b = _tiny(seed=11).simulate()
    assert a == b


def test_trotterization_simulator_str_and_repr():
    sim = _tiny()
    assert "TrotterizationSimulator(" in str(sim)
    assert "num_qubits=1" in str(sim)
    assert "num_steps=4" in str(sim)
    assert "TrotterizationSimulator(" in repr(sim)
    assert "time_steps=3" in repr(sim)


def test_trace_qubits_accepts_single_int_index():
    assert _trace_qubits({"01": 3, "11": 2}, 1) == {"1": 5}


def test_trace_qubits_grouped_list():
    traced = _trace_qubits({"01": 3, "11": 2}, [[0], 1])
    assert traced == [{"0": 3, "1": 2}, {"1": 5}]


def test_trotter_circuit_counts_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=0,
        )


def test_trotter_circuit_counts_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=1,
            seed=1.5,  # type: ignore[arg-type]
        )


def test_trotter_circuit_counts_rejects_nonpositive_num_steps():
    with pytest.raises(ValueError, match="num_steps must be a positive integer"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            t=0.0,
            num_steps=0,
            shots=1,
        )


def test_trotter_circuit_counts_rejects_nonpositive_trotter_depth():
    with pytest.raises(ValueError, match="trotter_depth must be a positive integer"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            trotter_depth=0,
            shots=1,
        )


def test_trotter_circuit_counts_verbose_prints_iterations(monkeypatch, capsys):
    _fake_aer_backend(monkeypatch)

    _trotter_circuit_counts(
        [LocalHamiltonian(Z, [0])],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        verbose=True,
        shots=1,
    )

    assert "Working on iteration 0 out of 1" in capsys.readouterr().out


# Single-term H=X is exact under first-order Trotter; residual is shot noise only.
TOTAL_TIME = 0.5
TIME_STEPS = 5
NUM_STEPS = 8
SHOTS = 2000
TOL_POP = 0.08


def test_trotterization_qutip_closed_agreement():
    psi0 = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    qutip_simulator = QutipSimulator(
        [Hamiltonian(X)],
        [],
        psi0,
        [Operator(ONE)],
        1,
        TOTAL_TIME,
        TIME_STEPS,
    )
    trotter_simulator = TrotterizationSimulator(
        [LocalHamiltonian(X, [0])],
        [],
        psi0,
        1,
        TOTAL_TIME,
        TIME_STEPS,
        NUM_STEPS,
        measurement_groups=[0],
        reducers=[population_one],
        shots=SHOTS,
        seed=0,
    )

    benchmark = Benchmark(qutip_simulator, trotter_simulator)
    benchmark.run()

    metrics = benchmark.error_metrics()
    assert len(metrics) == 1
    observables = metrics[0]["observables"]
    assert len(observables) == 1
    assert observables[0]["linf"] < TOL_POP, (
        f"|1> population: max abs error {observables[0]['linf']:.4f} exceeds tolerance {TOL_POP}"
    )
