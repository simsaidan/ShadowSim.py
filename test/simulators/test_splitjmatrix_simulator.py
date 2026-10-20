import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

import scipy.linalg

import shadowsim.backends.circuit as circuit_backend_module
import shadowsim.simulators.splitjmatrix_simulator as splitjmatrix_module
from shadowsim.core import LocalHamiltonian, LocalOperator, Operator, State
from shadowsim.simulators import SplitJMatrixSimulator
from shadowsim.simulators.reducers import expectation_x, expectation_z
from shadowsim.simulators.splitjmatrix_simulator import (
    _split_jmatrix,
    _trace_qubits,
    cavity_population,
    population_one,
)
from shadowsim.simulators.trotterization_simulator import _trotter_slice_unitaries

Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def _simulator(*, verbose=False, shots=10000, **kwargs):
    return SplitJMatrixSimulator(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        total_time=1.0,
        time_steps=2,
        num_steps=1,
        verbose=verbose,
        shots=shots,
        **kwargs,
    )


def test_splitjmatrix_simulator_is_quiet_by_default(monkeypatch, capsys):
    verbose_values = []

    def fake_split_jmatrix(*args, **kwargs):
        verbose_values.append(kwargs["verbose"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator().simulate()

    assert capsys.readouterr().out == ""
    assert verbose_values == [False, False]


def test_splitjmatrix_simulator_reports_progress_when_verbose(monkeypatch, capsys):
    verbose_values = []

    def fake_split_jmatrix(*args, **kwargs):
        verbose_values.append(kwargs["verbose"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(verbose=True).simulate()

    output = capsys.readouterr().out
    assert "Working on time step 0.0" in output
    assert "Working on time step 1.0" in output
    assert verbose_values == [True, True]


def test_splitjmatrix_simulator_forwards_shots(monkeypatch):
    seen_shots = []

    def fake_split_jmatrix(*args, **kwargs):
        seen_shots.append(kwargs["shots"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(shots=1234).simulate()

    assert seen_shots == [1234, 1234]


def test_splitjmatrix_simulator_forwards_seed(monkeypatch):
    seen_seeds = []

    def fake_split_jmatrix(*args, **kwargs):
        seen_seeds.append(kwargs["seed"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(seed=7).simulate()

    assert seen_seeds == [7, 7]


def test_splitjmatrix_simulator_progress_callback(monkeypatch):
    seen = []

    def fake_split_jmatrix(*args, **kwargs):
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(progress=lambda step, total: seen.append((step, total))).simulate()

    assert seen == [(0, 2), (1, 2)]


def test_splitjmatrix_simulator_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _simulator(shots=0)


@pytest.mark.parametrize("trotter_depth", [0, -1])
def test_splitjmatrix_simulator_rejects_nonpositive_trotter_depth(trotter_depth):
    with pytest.raises(ValueError, match="trotter_depth must be a positive integer"):
        _simulator(trotter_depth=trotter_depth)


def test_splitjmatrix_simulator_default_order_is_one():
    assert _simulator().order == 1


def test_splitjmatrix_simulator_rejects_unsupported_order():
    with pytest.raises(ValueError, match="order must be 1 or 2"):
        _simulator(order=3)  # type: ignore[arg-type]


def test_splitjmatrix_simulator_records_order(monkeypatch):
    seen = []

    def fake_split_jmatrix(*args, **kwargs):
        seen.append(kwargs["order"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    result = _simulator(order=2).simulate()

    assert seen == [2, 2]
    assert result.metadata["order"] == 2


def test_splitjmatrix_simulator_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _simulator(seed=1.5)  # type: ignore[arg-type]


def test_splitjmatrix_simulator_rejects_nonpositive_workers():
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        _simulator(workers=0)


def test_splitjmatrix_simulator_rejects_non_int_workers():
    with pytest.raises(TypeError, match="workers must be an int"):
        _simulator(workers=1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="workers must be an int"):
        _simulator(workers=True)  # type: ignore[arg-type]


def test_trace_qubits_accepts_single_int_index():
    assert _trace_qubits({"01": 3, "11": 2}, 1) == {"1": 5}


def test_split_j_rotates_the_body_qubit_for_x() -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"00": 1}

    backend = Recording()
    _split_jmatrix(
        [],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
        x_qubits=[0],
    )
    circuit = backend.circuit
    assert circuit is not None
    hadamards = [
        circuit.find_bit(instruction.qubits[0]).index
        for instruction in circuit.data
        if instruction.operation.name == "h"
    ]
    assert hadamards == [1]


def test_split_j_rejects_a_bad_x_qubit() -> None:
    state = State(np.array([1.0, 0.0]), 1)
    with pytest.raises(ValueError, match="x_qubits must be indexes from 0 to 0"):
        _split_jmatrix([], [], state, num_qubits=1, t=0.0, num_steps=1, shots=1, seed=0, x_qubits=[True])


def test_split_j_rotates_a_repeated_x_qubit_once() -> None:
    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"00": 1}

    backend = Recording()
    _split_jmatrix(
        [],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
        x_qubits=[0, 0],
    )
    circuit = backend.circuit
    assert circuit is not None
    hadamards = [
        circuit.find_bit(instruction.qubits[0]).index
        for instruction in circuit.data
        if instruction.operation.name == "h"
    ]
    assert hadamards == [1]


def test_population_one_and_cavity_population_empty_counts():
    assert population_one({}) == 0.0
    assert cavity_population({}) == 0.0
    assert expectation_z({}) == 0.0
    assert expectation_z({"0": 3, "1": 1}) == 0.5
    assert expectation_x({"0": 3, "1": 1}) == 0.5


def test_split_jmatrix_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=0,
        )


def test_split_jmatrix_rejects_unsupported_order():
    with pytest.raises(ValueError, match="order must be 1 or 2"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            order=3,  # type: ignore[arg-type]
            shots=1,
        )


@pytest.mark.parametrize("trotter_depth", [0, -1])
def test_split_jmatrix_rejects_nonpositive_trotter_depth(trotter_depth):
    with pytest.raises(ValueError, match="trotter_depth must be a positive integer"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=1.0,
            num_steps=1,
            trotter_depth=trotter_depth,
            shots=1,
        )


@pytest.mark.parametrize("order", [1, 2])
def test_split_jmatrix_repeats_hamiltonian_slice_to_cover_time_t(order: int) -> None:
    """Each step keeps one jump and repeats the Hamiltonian slice ``trotter_depth`` times."""

    class Recording:
        name = "recording"

        def __init__(self) -> None:
            self.circuit = None

        def run_counts(self, circuit: object, *, shots: int, seed: int | None) -> dict[str, int]:
            del shots, seed
            self.circuit = circuit
            return {"00": 1}

    X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
    lowering = np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128)
    backend = Recording()
    t = 1.0
    num_steps = 2
    trotter_depth = 2
    hamiltonians = [LocalHamiltonian(Z, [0]), LocalHamiltonian(X, [0])]
    _split_jmatrix(
        hamiltonians,
        [LocalOperator(lowering, [0])],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=t,
        num_steps=num_steps,
        trotter_depth=trotter_depth,
        order=order,  # type: ignore[arg-type]
        shots=1,
        seed=0,
        circuit_backend=backend,  # type: ignore[arg-type]
    )
    circuit = backend.circuit
    assert circuit is not None
    unitaries = [
        np.asarray(instruction.operation.params[0], dtype=np.complex128)
        for instruction in circuit.data
        if instruction.operation.name == "unitary"
    ]
    delta = t / (num_steps * trotter_depth)
    expected_h = [matrix for matrix, _sites in _trotter_slice_unitaries(hamiltonians, delta, order)]
    expected_h = expected_h * (num_steps * trotter_depth)
    size = lowering.shape[0]
    jump = np.block([[np.zeros((size, size)), lowering.conjugate().T], [lowering, np.zeros((size, size))]])
    expected_j = scipy.linalg.expm(-1j * jump * np.sqrt(t / num_steps))
    got_h = [matrix for matrix in unitaries if matrix.shape == (2, 2)]
    got_j = [matrix for matrix in unitaries if matrix.shape == (4, 4)]

    assert len(got_j) == num_steps
    for matrix in got_j:
        assert np.allclose(matrix, expected_j)
    assert len(got_h) == len(expected_h)
    for matrix, want in zip(got_h, expected_h, strict=True):
        assert np.allclose(matrix, want)


def test_split_jmatrix_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=1,
            seed=1.5,  # type: ignore[arg-type]
        )


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

    monkeypatch.setattr(circuit_backend_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(circuit_backend_module, "transpile", lambda circ, backend: circ)


def test_split_jmatrix_verbose_prints_iterations(monkeypatch, capsys):
    _fake_aer_backend(monkeypatch)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        verbose=True,
        shots=1,
    )

    assert "Working on iteration 0 out of 1" in capsys.readouterr().out


def test_split_jmatrix_passes_seed_simulator(monkeypatch):
    ctor_kwargs = []
    _fake_aer_backend(monkeypatch, ctor_kwargs_log=ctor_kwargs)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=7,
    )

    assert ctor_kwargs == [{"seed_simulator": 7}]


def test_split_jmatrix_omits_seed_when_none(monkeypatch):
    ctor_kwargs = []
    _fake_aer_backend(monkeypatch, ctor_kwargs_log=ctor_kwargs)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=None,
    )

    assert ctor_kwargs == [{}]


def test_splitjmatrix_simulator_run_settings_are_keyword_only():
    hamiltonians = [LocalHamiltonian(Z, [0])]
    state = State(np.array([1.0, 0.0]), 1)
    with pytest.raises(TypeError, match="positional"):
        SplitJMatrixSimulator(hamiltonians, [], state, 1)
    with pytest.raises(TypeError, match="positional"):
        SplitJMatrixSimulator(hamiltonians, [], state, 1, 1.0, 2, 1)

    sim = SplitJMatrixSimulator(
        hamiltonians,
        [],
        state,
        num_qubits=1,
        total_time=1.0,
        time_steps=2,
        num_steps=4,
    )
    assert sim.num_qubits == 1
    assert sim.total_time == 1.0
    assert sim.time_steps == 2
    assert sim.num_steps == 4


def test_splitjmatrix_simulator_rejects_non_local_lindblad():
    with pytest.raises(TypeError, match="must be LocalOperator"):
        SplitJMatrixSimulator(
            [LocalHamiltonian(Z, [0])],
            [Operator(Z)],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            total_time=1.0,
            time_steps=2,
            num_steps=1,
        )


def test_splitjmatrix_simulator_rejects_mismatched_reducers():
    with pytest.raises(ValueError, match="reducers and measurement_groups must have the same length"):
        _simulator(measurement_groups=[0], reducers=[population_one, population_one])


def test_splitjmatrix_simulator_str_and_repr():
    sim = _simulator(shots=42, seed=7)
    text = str(sim)
    rep = repr(sim)
    assert "SplitJMatrixSimulator(" in text
    assert "shots=42" in text
    assert "seed=7" in text
    assert "order=1" in text
    assert "SplitJMatrixSimulator(" in rep
    assert "shots=42" in rep
    assert "seed=7" in rep
    assert "workers=1" in rep
    assert "progress=" in rep
