"""Tests for the closed-system TrotterizationSimulator."""

import numpy as np
import pytest

import shadowsim.simulators.trotterization_simulator as trotter_module
from shadowsim.benchmarking import Benchmark
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, State
from shadowsim.simulators import QutipSimulator, TrotterizationSimulator, population_one
from shadowsim.simulators.simulator import Simulator

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
