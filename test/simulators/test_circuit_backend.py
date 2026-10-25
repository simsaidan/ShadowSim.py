"""Tests for CircuitBackend execution targets."""

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

from qiskit import QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit import Gate, Instruction
from qiskit.circuit.library import CXGate, RXGate, UnitaryGate
from qiskit_aer import AerSimulator

import shadowsim.backends.circuit as circuit_backend_module
from shadowsim.backends.circuit import AerCircuitBackend, QiskitCircuitBackend, from_qiskit, to_qiskit
from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Reset, Unitary
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import SplitJMatrixSimulator, TrotterizationSimulator

Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_SIMULATORS = [SplitJMatrixSimulator, TrotterizationSimulator]


def _settings(**kwargs):
    defaults = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.1,
        "time_steps": 1,
        "num_steps": 1,
        "shots": 4,
        "seed": 7,
    }
    defaults.update(kwargs)
    return defaults


def _forbid_aer(*args, **kwargs):
    raise AssertionError("AerSimulator was constructed")


class _RecordingBackend:
    """Return fixed counts and record each call."""

    def __init__(self):
        self.name = "recording"
        self.calls = []

    def run_counts(self, circuit, *, shots, seed):
        self.calls.append((shots, seed))
        return {"1": 4}


class _WrappedBackend:
    """Stand in for a BackendV2 whose run method is observable."""

    def __init__(self):
        self.runs = []

    def run(self, compiled, shots):
        self.runs.append((compiled, shots))

        class _Job:
            def result(self):
                class _Result:
                    def get_counts(self):
                        return {"1": 4}

                return _Result()

        return _Job()


@pytest.mark.parametrize("cls", _SIMULATORS)
def test_default_backend_passes_seed_simulator(monkeypatch, cls):
    ctor_kwargs = []

    class FakeResult:
        def get_counts(self):
            return {"0": 1}

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeBackend:
        def __init__(self, **kwargs):
            ctor_kwargs.append(kwargs)

        def run(self, compiled, shots):
            return FakeJob()

    monkeypatch.setattr(circuit_backend_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(circuit_backend_module, "transpile", lambda circ, backend: circ)

    result = cls(**_settings()).simulate()

    assert ctor_kwargs == [{"seed_simulator": 7}]
    assert result.metadata["circuit_backend"] == "aer"


def test_one_fake_backend_drives_both_simulators(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _forbid_aer)
    backend = _RecordingBackend()

    for cls in _SIMULATORS:
        result = cls(**_settings(circuit_backend=backend)).simulate()
        assert result.metadata["circuit_backend"] == "recording"
        np.testing.assert_allclose(result.observables[0], [1.0])

    assert backend.calls == [(4, 7), (4, 7)]


def test_qiskit_circuit_backend_runs_wrapped_backend(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _forbid_aer)
    wrapped = _WrappedBackend()
    transpiled_to = []

    def fake_transpile(circ, backend):
        transpiled_to.append(backend)
        return circ

    monkeypatch.setattr(circuit_backend_module, "transpile", fake_transpile)
    backend = QiskitCircuitBackend(wrapped, name="lab")

    for cls in _SIMULATORS:
        result = cls(**_settings(circuit_backend=backend)).simulate()
        assert result.metadata["circuit_backend"] == "lab"

    assert transpiled_to == [wrapped, wrapped]
    assert len(wrapped.runs) == 2
    assert all(shots == 4 for _compiled, shots in wrapped.runs)


def test_qiskit_circuit_backend_requires_get_counts(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "transpile", lambda circ, backend: circ)

    class _Result:
        pass

    class _Job:
        def result(self):
            return _Result()

    class _Backend:
        def run(self, compiled, shots):
            return _Job()

    circuit = QuantumCircuit(1)
    circuit.measure_all()
    with pytest.raises(TypeError, match="get_counts"):
        QiskitCircuitBackend(_Backend()).run_counts(circuit, shots=1, seed=1)


def _permutation_matrix() -> np.ndarray:
    return np.array(
        [
            [0, 0, 0, 1],
            [0, 0, 1, 0],
            [0, 1, 0, 0],
            [1, 0, 0, 0],
        ],
        dtype=np.complex128,
    )


def _two_register_circuit() -> tuple[QuantumCircuit, np.ndarray]:
    ancilla = QuantumRegister(1, "anc")
    body = QuantumRegister(1, "q")
    circuit = QuantumCircuit(ancilla, body)
    matrix = _permutation_matrix()
    circuit.initialize([1, 0], [body[0]])
    circuit.append(UnitaryGate(matrix), [ancilla[0], body[0]])
    circuit.reset(ancilla[0])
    circuit.h(body[0])
    circuit.barrier()
    circuit.measure_all()
    return circuit, matrix


def test_qiskit_round_trip_preserves_operations():
    circuit, matrix = _two_register_circuit()
    expected = Program(
        2,
        2,
        [
            Prepare([1, 0], [1]),
            Unitary(matrix, [0, 1]),
            Reset(0),
            Hadamard(1),
            Barrier([0, 1]),
            Barrier([0, 1]),
            Measure(0, 0),
            Measure(1, 1),
        ],
    )

    program = from_qiskit(circuit)

    assert program == expected
    assert from_qiskit(to_qiskit(program)) == program


def test_from_qiskit_records_gates_as_their_matrices():
    circuit = QuantumCircuit(2)
    circuit.rx(0.3, 0)
    circuit.cx(0, 1)

    program = from_qiskit(circuit)

    assert program.operations == (
        Unitary(RXGate(0.3).to_matrix(), [0]),
        Unitary(CXGate().to_matrix(), [0, 1]),
    )
    assert from_qiskit(to_qiskit(program)) == program


def test_from_qiskit_rejects_a_gate_without_a_matrix():
    circuit = QuantumCircuit(1)
    circuit.append(Gate("black_box", 1, []), [0])

    with pytest.raises(ValueError, match="'black_box'"):
        from_qiskit(circuit)


def test_from_qiskit_rejects_an_instruction_without_to_matrix():
    circuit = QuantumCircuit(1)
    circuit.append(Instruction("plain", 1, 0, []), [0])

    with pytest.raises(ValueError, match="'plain'"):
        from_qiskit(circuit)


class _VectorGate(Gate):
    """Gate whose matrix is a vector, so it cannot be recorded as a unitary."""

    def __init__(self) -> None:
        super().__init__("vector", 1, [])

    def to_matrix(self) -> np.ndarray:
        return np.ones(2)


def test_from_qiskit_rejects_a_matrix_that_is_not_square():
    circuit = QuantumCircuit(1)
    circuit.append(_VectorGate(), [0])

    with pytest.raises(ValueError, match="'vector'"):
        from_qiskit(circuit)


def test_to_qiskit_rejects_an_unknown_operation():
    program = Program(1, 0, [])
    program.operations = ("not-an-operation",)

    with pytest.raises(TypeError, match="got str"):
        to_qiskit(program)


def _aer_counts(circuit: QuantumCircuit) -> dict[str, int]:
    backend = AerSimulator(seed_simulator=3)
    return backend.run(transpile(circuit, backend), shots=64).result().get_counts()


def test_round_trip_preserves_aer_counts():
    circuit, _matrix = _two_register_circuit()

    assert _aer_counts(to_qiskit(from_qiskit(circuit))) == _aer_counts(circuit)


def test_backends_transpile_the_rebuilt_circuit(monkeypatch):
    seen = []

    def fake_transpile(circ, backend):
        del backend
        seen.append(circ)
        return circ

    class _CountingBackend:
        def __init__(self, **kwargs):
            del kwargs

        def run(self, compiled, shots):
            del compiled, shots

            class _Job:
                def result(self):
                    class _Result:
                        def get_counts(self):
                            return {"0": 1}

                    return _Result()

            return _Job()

    monkeypatch.setattr(circuit_backend_module, "transpile", fake_transpile)
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _CountingBackend)
    circuit, _matrix = _two_register_circuit()
    expected = from_qiskit(circuit)

    AerCircuitBackend().run_counts(circuit, shots=1, seed=1)
    QiskitCircuitBackend(_CountingBackend()).run_counts(circuit, shots=1, seed=None)

    assert seen[0] is not circuit
    assert seen[1] is not circuit
    assert [from_qiskit(circ) for circ in seen] == [expected, expected]


def test_backends_reject_a_gate_without_a_matrix_before_running(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _forbid_aer)
    circuit = QuantumCircuit(1)
    circuit.append(Gate("black_box", 1, []), [0])

    with pytest.raises(ValueError, match="'black_box'"):
        AerCircuitBackend().run_counts(circuit, shots=1, seed=1)
    with pytest.raises(ValueError, match="'black_box'"):
        QiskitCircuitBackend(_WrappedBackend()).run_counts(circuit, shots=1, seed=1)


def test_aer_backend_runs_rx():
    circuit = QuantumCircuit(1)
    circuit.rx(0.3, 0)
    circuit.measure_all()

    assert AerCircuitBackend().run_counts(circuit, shots=64, seed=3) == _aer_counts(circuit)


def test_aer_backend_matches_direct_counts():
    circuit, _matrix = _two_register_circuit()

    assert AerCircuitBackend().run_counts(circuit, shots=64, seed=3) == _aer_counts(circuit)
