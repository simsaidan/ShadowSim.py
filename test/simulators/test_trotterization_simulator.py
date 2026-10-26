"""Tests for the closed-system TrotterizationSimulator."""

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

import scipy.linalg

import shadowsim.backends.aer as aer_backend_module
import shadowsim.simulators.trotterization_simulator as trotter_module
from shadowsim.benchmarking import Benchmark
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, State
from shadowsim.simulators import TrotterizationSimulator, expectation_z, population_one
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import (
    _trace_qubits,
    _trotter_circuit_counts,
    _trotter_slice_unitaries,
)

Z = np.diag([1.0, -1.0]).astype(np.complex128)
X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
ONE = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=np.complex128)


def _tiny(**kwargs):
    shots = kwargs.pop("shots", 256)
    backend = kwargs.get("circuit_backend")
    if backend is None:
        kwargs["circuit_backend"] = aer_backend_module.AerCircuitBackend(shots=shots)
    else:
        backend.shots = shots
    defaults = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.1,
        "time_steps": 3,
        "num_steps": 4,
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

    monkeypatch.setattr(aer_backend_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(aer_backend_module, "transpile", lambda circ, backend: circ)


def test_trotterization_simulator_is_simulator():
    sim = _tiny()
    assert isinstance(sim, Simulator)
    assert sim.id == "trotterization_simulator"


def test_trotterization_simulator_run_settings_are_keyword_only():
    hamiltonians = [LocalHamiltonian(Z, [0])]
    state = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    with pytest.raises(TypeError, match="positional"):
        TrotterizationSimulator(hamiltonians, [], state, 1)
    with pytest.raises(TypeError, match="positional"):
        TrotterizationSimulator(hamiltonians, [], state, 1, 0.1, 3, 4)

    sim = TrotterizationSimulator(
        hamiltonians,
        [],
        state,
        num_qubits=1,
        total_time=0.1,
        time_steps=3,
        num_steps=4,
    )
    assert sim.num_qubits == 1
    assert sim.total_time == 0.1
    assert sim.time_steps == 3
    assert sim.num_steps == 4


def test_trotterization_simulator_rejects_lindblads():
    with pytest.raises(ValueError, match="closed-system"):
        _tiny(lindblads=[Operator(Z)])


def test_trotterization_simulator_rejects_non_local_hamiltonian():
    with pytest.raises(TypeError, match="LocalHamiltonian"):
        _tiny(hamiltonians=[Hamiltonian(Z)])


def test_trotterization_simulator_reads_pauli_expectations():
    class Expectations:
        name = "expectations"

        def __init__(self) -> None:
            self.qubits: list[list[int]] = []
            self.measured = False

        def z_expectations(self, circuit, qubits, *, shots, seed):
            self.qubits.append(list(qubits))
            self.measured = any(instruction.operation.name == "measure" for instruction in circuit.data)
            return [0.5 for _ in qubits]

        def run_counts(self, circuit, *, shots, seed):
            raise AssertionError("counts")

    backend = Expectations()
    shared = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.2,
        "time_steps": 2,
        "num_steps": 1,
        "seed": 3,
        "circuit_backend": backend,
    }
    simulator = TrotterizationSimulator(
        **shared,
        measurement_groups=[0],
        reducers=[expectation_z],
    )
    expectations = simulator.simulate()
    populations = TrotterizationSimulator(
        **shared,
        measurement_groups=[[0]],
        reducers=[population_one],
    ).simulate()

    assert expectations.observables[0].tolist() == [0.5, 0.5]
    assert populations.observables[0].tolist() == [0.25, 0.25]
    assert backend.qubits == [[0], [0], [0], [0]]
    assert backend.measured is False
    assert "shots=" not in str(simulator)


def test_trotterization_simulator_rejects_a_joint_pauli_group():
    class Expectations:
        name = "expectations"

        def z_expectations(self, circuit, qubits, *, shots, seed):
            raise AssertionError("expectations")

    with pytest.raises(ValueError, match="one qubit"):
        TrotterizationSimulator(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            total_time=0.1,
            time_steps=1,
            num_steps=1,
            measurement_groups=[[0, 0]],
            reducers=[population_one],
            circuit_backend=Expectations(),  # type: ignore[arg-type]
        ).simulate()


def test_trotterization_simulator_rejects_parallel_pauli_runs():
    class Expectations:
        name = "expectations"

    with pytest.raises(ValueError, match="calling process"):
        TrotterizationSimulator(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            total_time=0.1,
            time_steps=1,
            num_steps=1,
            workers=2,
            circuit_backend=Expectations(),  # type: ignore[arg-type]
        )


def test_trotterization_simulator_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _tiny(shots=0)


def test_trotterization_simulator_rejects_nonpositive_num_steps():
    with pytest.raises(ValueError, match="num_steps must be a positive integer"):
        _tiny(num_steps=0)


def test_trotterization_simulator_rejects_nonpositive_trotter_depth():
    with pytest.raises(ValueError, match="trotter_depth must be a positive integer"):
        _tiny(trotter_depth=0)


def test_trotterization_simulator_default_order_is_one():
    assert _tiny().order == 1


def test_trotterization_simulator_rejects_unsupported_order():
    with pytest.raises(ValueError, match="order must be 1 or 2"):
        _tiny(order=3)  # type: ignore[arg-type]


def test_trotterization_simulator_records_order(monkeypatch):
    seen = []

    def fake_counts(*args, **kwargs):
        seen.append(kwargs["order"])
        return {"0": 10}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    result = _tiny(order=2, time_steps=1).simulate()

    assert seen == [2]
    assert result.metadata["order"] == 2


def test_trotterization_simulator_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _tiny(seed=1.5)  # type: ignore[arg-type]


def test_trotterization_simulator_rejects_nonpositive_workers():
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        _tiny(workers=0)


def test_trotterization_simulator_rejects_non_int_workers():
    with pytest.raises(TypeError, match="workers must be an int"):
        _tiny(workers=1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="workers must be an int"):
        _tiny(workers=True)  # type: ignore[arg-type]


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


def test_trotter_circuit_rotates_x_qubits_before_measurement() -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"0": 1}

    backend = Recording()
    _trotter_circuit_counts(
        [LocalHamiltonian(Z, [0])],
        State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2),
        2,
        0.0,
        1,
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
        x_qubits=[1],
    )
    circuit = backend.circuit
    assert circuit is not None
    hadamards = [
        circuit.find_bit(instruction.qubits[0]).index
        for instruction in circuit.data
        if instruction.operation.name == "h"
    ]
    assert hadamards == [1]


def test_trotter_circuit_rejects_a_bad_x_qubit() -> None:
    state = State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2)
    with pytest.raises(ValueError, match="x_qubits must be indexes from 0 to 1"):
        _trotter_circuit_counts([LocalHamiltonian(Z, [0])], state, 2, 0.0, 1, shots=1, seed=0, x_qubits=[2])


def test_trotter_circuit_rotates_a_repeated_x_qubit_once() -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"00": 1}

    backend = Recording()
    _trotter_circuit_counts(
        [LocalHamiltonian(Z, [0])],
        State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2),
        2,
        0.0,
        1,
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
        x_qubits=[1, 1],
    )
    circuit = backend.circuit
    assert circuit is not None
    hadamards = [
        circuit.find_bit(instruction.qubits[0]).index
        for instruction in circuit.data
        if instruction.operation.name == "h"
    ]
    assert hadamards == [1]


def test_trotterization_simulator_grouped_measurement_groups(monkeypatch):
    def fake_counts(*args, **kwargs):
        return {"0": 7, "1": 3}

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)

    results = _tiny(
        time_steps=1,
        measurement_groups=[[0]],
        reducers=[population_one],
    ).simulate()

    assert len(results.observables) == 1
    assert len(results.observables[0]) == 1
    assert results.observables[0][0] == pytest.approx(0.3)


def test_trotterization_simulator_simulate_smoke():
    sim = _tiny()
    results = sim.simulate()
    assert len(results.observables) == 1
    assert len(results.observables[0]) == 3
    assert all(0.0 <= x <= 1.0 for x in results.observables[0])


def test_trotterization_simulator_seed_reproducible():
    a = _tiny(seed=11).simulate()
    b = _tiny(seed=11).simulate()
    assert np.allclose(a.observables, b.observables)
    assert a.seed == b.seed == 11


def test_trotterization_simulator_str_and_repr():
    sim = _tiny()
    assert "TrotterizationSimulator(" in str(sim)
    assert "num_qubits=1" in str(sim)
    assert "num_steps=4" in str(sim)
    assert "TrotterizationSimulator(" in repr(sim)
    assert "time_steps=3" in repr(sim)
    assert "workers=1" in repr(sim)


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


def test_trotter_circuit_counts_rejects_unsupported_order():
    with pytest.raises(ValueError, match="order must be 1 or 2"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=1,
            order=3,  # type: ignore[arg-type]
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


def _product_unitary(hamiltonians, t, num_steps, trotter_depth, order):
    """Multiply one-qubit slice unitaries. The first slice factor is applied first."""
    delta = t / (num_steps * trotter_depth)
    steps = _trotter_slice_unitaries(hamiltonians, delta, order)
    unitary = np.eye(2, dtype=np.complex128)
    for _ in range(num_steps * trotter_depth):
        for matrix, _sites in steps:
            unitary = matrix @ unitary
    return unitary


def test_order_one_slice_matches_first_order_product():
    terms = [LocalHamiltonian(X, [0]), LocalHamiltonian(Z, [1])]
    delta = 0.25
    steps = _trotter_slice_unitaries(terms, delta, 1)

    assert [sites for _matrix, sites in steps] == [[0], [1]]
    assert np.allclose(steps[0][0], scipy.linalg.expm(-1j * X * delta))
    assert np.allclose(steps[1][0], scipy.linalg.expm(-1j * Z * delta))


def test_order_two_slice_is_strang():
    terms = [LocalHamiltonian(X, [0]), LocalHamiltonian(Y, [1]), LocalHamiltonian(Z, [0])]
    delta = 0.4
    steps = _trotter_slice_unitaries(terms, delta, 2)
    expected = [
        (scipy.linalg.expm(-1j * X * delta / 2), [0]),
        (scipy.linalg.expm(-1j * Y * delta / 2), [1]),
        (scipy.linalg.expm(-1j * Z * delta), [0]),
        (scipy.linalg.expm(-1j * Y * delta / 2), [1]),
        (scipy.linalg.expm(-1j * X * delta / 2), [0]),
    ]

    assert [sites for _matrix, sites in steps] == [sites for _matrix, sites in expected]
    for got, want in zip(steps, expected, strict=True):
        assert np.allclose(got[0], want[0])


@pytest.mark.parametrize("order", [1, 2])
def test_single_term_product_is_exact(order):
    term = [LocalHamiltonian(X, [0])]
    t = 0.7
    num_steps = 4
    trotter_depth = 3
    got = _product_unitary(term, t, num_steps, trotter_depth, order)
    exact = scipy.linalg.expm(-1j * X * t)
    assert np.linalg.norm(got - exact) < 1e-8


def test_order_two_is_closer_than_order_one_for_noncommuting_terms():
    terms = [LocalHamiltonian(X, [0]), LocalHamiltonian(Z, [0])]
    t = 1.0
    num_steps = 2
    trotter_depth = 2
    exact = scipy.linalg.expm(-1j * (X + Z) * t)
    err1 = np.linalg.norm(_product_unitary(terms, t, num_steps, trotter_depth, 1) - exact)
    err2 = np.linalg.norm(_product_unitary(terms, t, num_steps, trotter_depth, 2) - exact)

    assert err1 > 1e-6
    assert err2 < err1


@pytest.mark.parametrize("order", [1, 2])
def test_circuit_repeats_slice_unitaries(monkeypatch, order):
    captured = []

    class FakeResult:
        def get_counts(self):
            return {"0": 1}

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeBackend:
        def run(self, compiled, shots):
            captured.append(compiled)
            return FakeJob()

    monkeypatch.setattr(aer_backend_module, "AerSimulator", lambda *args, **kwargs: FakeBackend())
    monkeypatch.setattr(aer_backend_module, "transpile", lambda circ, backend: circ)

    terms = [LocalHamiltonian(X, [0]), LocalHamiltonian(Z, [0])]
    t = 0.5
    num_steps = 2
    trotter_depth = 3
    _trotter_circuit_counts(
        terms,
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        t=t,
        num_steps=num_steps,
        trotter_depth=trotter_depth,
        order=order,
        shots=1,
    )

    delta = t / (num_steps * trotter_depth)
    expected = [matrix for matrix, _sites in _trotter_slice_unitaries(terms, delta, order)]
    expected = expected * (num_steps * trotter_depth)
    got = [
        np.asarray(instruction.operation.params[0], dtype=np.complex128)
        for instruction in captured[0].data
        if instruction.operation.name == "unitary"
    ]

    assert len(got) == len(expected)
    for matrix, want in zip(got, expected, strict=True):
        assert np.allclose(matrix, want)


# Single-term H=X is exact under first-order Trotter; residual is shot noise only.
TOTAL_TIME = 0.5
TIME_STEPS = 5
NUM_STEPS = 8
SHOTS = 2000
TOL_POP = 0.08


@pytest.mark.cross_extra
def test_trotterization_qutip_closed_agreement():
    pytest.importorskip("qutip")
    from shadowsim.simulators import QutipSimulator

    psi0 = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    qutip_simulator = QutipSimulator(
        [Hamiltonian(X)],
        [],
        psi0,
        [Operator(ONE)],
        num_qubits=1,
        total_time=TOTAL_TIME,
        time_steps=TIME_STEPS,
    )
    trotter_simulator = TrotterizationSimulator(
        [LocalHamiltonian(X, [0])],
        [],
        psi0,
        num_qubits=1,
        total_time=TOTAL_TIME,
        time_steps=TIME_STEPS,
        num_steps=NUM_STEPS,
        measurement_groups=[0],
        reducers=[population_one],
        seed=0,
        circuit_backend=aer_backend_module.AerCircuitBackend(shots=SHOTS),
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
