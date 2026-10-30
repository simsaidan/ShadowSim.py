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
from shadowsim.simulators import (
    Measurement,
    TrotterizationSimulator,
    apply_measurements,
)
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import (
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
    simulator = TrotterizationSimulator(**shared)
    expectations = simulator.simulate()

    assert expectations.observables[0].tolist() == [0.5, 0.5]
    assert backend.qubits == [[0], [0]]
    assert backend.measured is False
    assert expectations.counts is None
    assert "shots=" not in str(simulator)
    with pytest.raises(ValueError, match="the expectations backend returns Pauli expectations"):
        apply_measurements(expectations, [Measurement((0,), 'counts["0"] / shots')])


def test_expectation_backend_reads_every_qubit_without_groups():
    class Expectations:
        name = "expectations"

        def __init__(self) -> None:
            self.qubits: list[list[int]] = []

        def z_expectations(self, circuit, qubits, *, shots, seed):
            self.qubits.append(list(qubits))
            return [0.5, -0.25]

    backend = Expectations()
    simulator = TrotterizationSimulator(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2),
        num_qubits=2,
        total_time=0.2,
        time_steps=2,
        num_steps=1,
        circuit_backend=backend,
    )
    simulated = simulator.simulate()

    assert backend.qubits == [[0, 1], [0, 1]]
    assert simulated.metadata["observable_kind"] == "qubit_expectations"
    assert [curve.tolist() for curve in simulated.observables] == [[0.5, 0.5], [-0.25, -0.25]]
    measured = simulator.measure([Measurement.population(1), Measurement.expectation(0)])
    assert [curve.tolist() for curve in measured.observables] == [[0.625, 0.625], [0.5, 0.5]]
    assert "observable_kind" not in measured.metadata
    assert simulator.last_result is measured
    assert [curve.tolist() for curve in simulator.get_results()] == [[0.625, 0.625], [0.5, 0.5]]
    again = simulator.measure([Measurement.expectation(1)])
    assert again.observables[0].tolist() == [-0.25, -0.25]
    with pytest.raises(ValueError, match="returns Pauli expectations, not shot counts"):
        simulator.measure([Measurement((0,), 'counts["0"] / shots')])
    with pytest.raises(ValueError, match="returns Pauli expectations, not shot counts"):
        simulator.measure([Measurement((0, 1), '(counts["00"] - counts["11"]) / shots')])
    with pytest.raises(ValueError, match="the result has 2 qubits, but this measurement reads qubit 2"):
        simulator.measure([Measurement.expectation(2)])


def test_measure_needs_a_simulation_first():
    with pytest.raises(ValueError, match="run the simulation first"):
        _tiny().measure([Measurement.population(0)])


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


def _instruction_signature(circuit: object) -> list[tuple[str, tuple[int, ...], tuple[bytes, ...]]]:
    """Return gate names, qubit indexes, and parameter bytes, ignoring register names."""
    rows: list[tuple[str, tuple[int, ...], tuple[bytes, ...]]] = []
    for instruction in circuit.data:  # type: ignore[attr-defined]
        qubits = tuple(int(circuit.find_bit(qubit).index) for qubit in instruction.qubits)  # type: ignore[attr-defined]
        params = tuple(np.asarray(param).tobytes() for param in instruction.operation.params)
        rows.append((instruction.operation.name, qubits, params))
    return rows


def test_metrics_circuit_matches_the_final_sampling_circuit() -> None:
    class Recording:
        name = "recording"
        shots = 1

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"0": 1}

    backend = Recording()
    sim = _tiny(circuit_backend=backend, time_steps=3, total_time=0.4, basis="X")
    _trotter_circuit_counts(
        sim.hamiltonians,
        sim.initial_state,
        sim.num_qubits,
        float(sim.tlist[-1]),
        sim.num_steps,
        sim.trotter_depth,
        order=sim.order,
        shots=1,
        seed=sim.seed,
        circuit_backend=backend,  # type: ignore[arg-type]
        basis=sim.basis,
    )
    assert _instruction_signature(sim.metrics_circuit()) == _instruction_signature(backend.circuit)


def test_metrics_circuit_omits_measurement_without_a_shot_budget() -> None:
    class Bare:
        name = "bare"

    sim = TrotterizationSimulator(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.4,
        time_steps=3,
        num_steps=1,
        circuit_backend=Bare(),  # type: ignore[arg-type]
    )
    names = [instruction.operation.name for instruction in sim.metrics_circuit().data]
    assert "measure" not in names


def _measured_rotations(basis: str) -> list[tuple[str, int]]:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"0" * len(basis): 1}

    backend = Recording()
    num_qubits = len(basis)
    state = np.zeros(2**num_qubits, dtype=np.complex128)
    state[0] = 1.0
    _trotter_circuit_counts(
        [LocalHamiltonian(Z, [0])],
        State(state, num_qubits),
        num_qubits,
        0.0,
        1,
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
        basis=basis,
    )
    circuit = backend.circuit
    assert circuit is not None
    return [
        (instruction.operation.name, circuit.find_bit(instruction.qubits[0]).index)
        for instruction in circuit.data
        if instruction.operation.name in {"h", "sdg"}
    ]


def test_trotter_circuit_rotates_each_qubit_into_its_basis() -> None:
    assert _measured_rotations("ZXY") == [("h", 1), ("sdg", 2), ("h", 2)]


def test_trotter_circuit_measures_z_by_default() -> None:
    assert _measured_rotations("ZZ") == []


@pytest.mark.parametrize("basis", ["Z", "ZZZ", "ZQ", "zx", 7])
def test_trotter_circuit_rejects_a_bad_basis(basis: object) -> None:
    state = State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2)
    with pytest.raises(ValueError, match="basis must be 2 letters from X, Y, and Z"):
        _trotter_circuit_counts(
            [LocalHamiltonian(Z, [0])],
            state,
            2,
            0.0,
            1,
            shots=1,
            seed=0,
            basis=basis,  # type: ignore[arg-type]
        )


def test_trotterization_simulator_rejects_a_bad_basis() -> None:
    with pytest.raises(ValueError, match="basis must be 1 letters"):
        _tiny(basis="XZ")


@pytest.mark.parametrize(
    ("basis", "expected"),
    [("Z", 1.0), ("X", 0.0), ("Y", 0.0)],
)
def test_trotterization_simulator_reads_the_chosen_basis(basis: str, expected: float) -> None:
    simulator = _tiny(basis=basis, time_steps=1, total_time=0.0, shots=4000)
    assert simulator.simulate().metadata["basis"] == basis
    result = simulator.measure([Measurement.expectation(0)])
    assert result.observables[0][0] == pytest.approx(expected, abs=0.08)


def test_trotterization_simulator_keeps_counts_per_time_point(monkeypatch):
    seen = iter([{"10": 3, "00": 1}, {"01": 4}])

    def fake_counts(*args, **kwargs):
        return next(seen)

    monkeypatch.setattr(trotter_module, "_trotter_circuit_counts", fake_counts)
    state = State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2)

    simulator = _tiny(initial_state=state, num_qubits=2, time_steps=2)
    result = simulator.simulate()

    assert result.counts == [{"01": 3, "00": 1}, {"10": 4}]
    assert result.observables == []
    measured = simulator.measure([Measurement.population(1), Measurement((0, 1), 'counts["00"] / shots')])
    assert [curve.tolist() for curve in measured.observables] == [[0.75, 0.0], [0.25, 0.0]]


def test_trotterization_simulator_simulate_smoke():
    sim = _tiny()
    results = sim.simulate()
    assert results.observables == []
    assert results.counts is not None
    assert len(results.counts) == 3
    populations = sim.measure([Measurement.population(0)]).observables
    assert len(populations) == 1
    assert all(0.0 <= x <= 1.0 for x in populations[0])


def test_trotterization_simulator_seed_reproducible():
    a = _tiny(seed=11).simulate()
    b = _tiny(seed=11).simulate()
    assert a.counts == b.counts
    assert a.seed == b.seed == 11


def test_trotterization_simulator_str_and_repr():
    sim = _tiny()
    assert "TrotterizationSimulator(" in str(sim)
    assert "num_qubits=1" in str(sim)
    assert "num_steps=4" in str(sim)
    assert "TrotterizationSimulator(" in repr(sim)
    assert "time_steps=3" in repr(sim)
    assert "workers=1" in repr(sim)


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
        seed=0,
        circuit_backend=aer_backend_module.AerCircuitBackend(shots=SHOTS),
    )

    benchmark = Benchmark(qutip_simulator, trotter_simulator)
    benchmark.run()
    trotter_simulator.measure([Measurement.population(0)])

    metrics = benchmark.error_metrics()
    assert len(metrics) == 1
    observables = metrics[0]["observables"]
    assert len(observables) == 1
    assert observables[0]["linf"] < TOL_POP, (
        f"|1> population: max abs error {observables[0]['linf']:.4f} exceeds tolerance {TOL_POP}"
    )
