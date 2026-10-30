"""Tests for the Cirq circuit backend."""

import numpy as np
import pytest

pytestmark = [pytest.mark.qiskit, pytest.mark.cirq, pytest.mark.cross_extra]

pytest.importorskip("qiskit")
pytest.importorskip("cirq")

from qiskit import QuantumCircuit
from qiskit.circuit import Gate, Instruction

from shadowsim import backends
from shadowsim.backends.cirq import CirqCircuitBackend


class _VectorGate(Gate):
    """Gate whose matrix is a vector, so it cannot be applied."""

    def __init__(self) -> None:
        super().__init__("vector", 1, [])

    def to_matrix(self) -> np.ndarray:
        return np.ones(2)


class _BrokenGate(Gate):
    """Gate whose matrix method fails."""

    def __init__(self) -> None:
        super().__init__("broken", 1, [])

    def to_matrix(self) -> np.ndarray:
        raise ValueError("no matrix")


class _GlobalPhase(Gate):
    """One-by-one phase on a register with no qubits."""

    def __init__(self) -> None:
        super().__init__("phase", 0, [])

    def to_matrix(self) -> np.ndarray:
        return np.ones((1, 1), dtype=complex)


def test_cirq_backend_is_exported() -> None:
    backend = CirqCircuitBackend()

    assert backends.CirqCircuitBackend is CirqCircuitBackend
    assert "CirqCircuitBackend" in dir(backends)
    assert backend.name == "cirq"
    assert not hasattr(backend, "shots")


def test_expectations_are_exact_and_ignore_shots_and_seed() -> None:
    circuit = QuantumCircuit(1)
    circuit.rx(0.4, 0)
    backend = CirqCircuitBackend()

    assert backend.z_expectations(circuit, [0], shots=1, seed=0) == pytest.approx([np.cos(0.4)])
    assert backend.z_expectations(circuit, [0], shots=99, seed=1) == pytest.approx([np.cos(0.4)])
    assert backend.x_expectations(circuit, [0], shots=3, seed=None) == pytest.approx([0.0])
    assert backend.z_expectations(circuit, [], shots=1, seed=None) == []


def test_run_counts_uses_qiskit_bit_order_and_the_seed() -> None:
    hadamard = QuantumCircuit(1, 1)
    hadamard.h(0)
    hadamard.measure(0, 0)
    excited = QuantumCircuit(2)
    excited.x(1)
    backend = CirqCircuitBackend()

    first = backend.run_counts(hadamard, shots=20, seed=0)
    assert first == backend.run_counts(hadamard, shots=20, seed=0)
    assert set(first) <= {"0", "1"}
    assert sum(first.values()) == 20
    assert backend.run_counts(excited, shots=2, seed=0) == {"10": 2}
    unseeded = backend.run_counts(excited, shots=3, seed=None)
    assert unseeded == {"10": 3}


def test_reset_and_a_mid_circuit_measure_are_rejected() -> None:
    reset = QuantumCircuit(1)
    reset.reset(0)
    measured = QuantumCircuit(1, 1)
    measured.measure(0, 0)
    measured.h(0)
    backend = CirqCircuitBackend()

    with pytest.raises(NotImplementedError, match="Reset is not supported"):
        backend.z_expectations(reset, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="measurement before the end"):
        backend.run_counts(measured, shots=1, seed=0)


def test_prepare_after_a_gate_and_a_bad_amplitude_vector_are_rejected() -> None:
    moved = QuantumCircuit(1)
    moved.h(0)
    moved.initialize([0.0, 1.0], 0)
    short = QuantumCircuit(1)
    short.append(Instruction("initialize", 1, 0, [1.0, 0.0, 0.0]), [0])
    backend = CirqCircuitBackend()

    with pytest.raises(NotImplementedError, match="Prepare after the state has left"):
        backend.z_expectations(moved, [0], shots=1, seed=None)
    with pytest.raises(ValueError, match="Prepare amplitudes must have shape"):
        backend.x_expectations(short, [0], shots=1, seed=None)


def test_run_counts_rejects_a_state_whose_probabilities_do_not_sum_to_one() -> None:
    circuit = QuantumCircuit(1)
    circuit.append(Instruction("initialize", 1, 0, [0.0, 0.0]), [0])

    with pytest.raises(ValueError, match="probabilities must sum to 1"):
        CirqCircuitBackend().run_counts(circuit, shots=1, seed=0)


def test_an_instruction_without_a_matrix_is_rejected() -> None:
    circuit = QuantumCircuit(1)
    circuit.append(Instruction("snap", 1, 0, []), [0])

    with pytest.raises(ValueError, match="unsupported instruction 'snap'"):
        CirqCircuitBackend().z_expectations(circuit, [0], shots=1, seed=None)


def test_a_matrix_that_is_not_square_is_rejected() -> None:
    circuit = QuantumCircuit(1)
    circuit.append(_VectorGate(), [0])

    with pytest.raises(ValueError, match="unsupported instruction 'vector'"):
        CirqCircuitBackend().z_expectations(circuit, [0], shots=1, seed=None)


def test_a_rotation_with_a_non_numeric_angle_is_rejected() -> None:
    circuit = QuantumCircuit(1)
    circuit.append(Instruction("rx", 1, 0, ["angle"]), [0])

    with pytest.raises(ValueError, match="unsupported instruction 'rx'"):
        CirqCircuitBackend().z_expectations(circuit, [0], shots=1, seed=None)


def test_run_counts_samples_an_empty_register() -> None:
    circuit = QuantumCircuit(0)
    circuit.append(_GlobalPhase(), [])

    assert CirqCircuitBackend().run_counts(circuit, shots=2, seed=0) == {"": 2}


def test_a_matrix_that_cannot_be_built_is_rejected() -> None:
    circuit = QuantumCircuit(1)
    circuit.append(_BrokenGate(), [0])

    with pytest.raises(ValueError, match="unsupported instruction 'broken'"):
        CirqCircuitBackend().z_expectations(circuit, [0], shots=1, seed=None)


@pytest.mark.parametrize(("name", "qubits"), [("h", [0, 1]), ("cx", [0]), ("rx", [0, 1])])
def test_a_named_gate_on_the_wrong_number_of_qubits_is_rejected(name: str, qubits: list[int]) -> None:
    circuit = QuantumCircuit(2)
    circuit.append(Instruction(name, len(qubits), 0, []), qubits)

    with pytest.raises(ValueError, match=f"unsupported instruction '{name}'"):
        CirqCircuitBackend().z_expectations(circuit, [0], shots=1, seed=None)


@pytest.mark.parametrize("qubit", [True, 1.5, -1, 1])
def test_expectations_reject_a_bad_qubit_index(qubit: object) -> None:
    circuit = QuantumCircuit(1)

    with pytest.raises(ValueError, match="outside a circuit of 1 qubits"):
        CirqCircuitBackend().x_expectations(circuit, [qubit], shots=1, seed=None)


@pytest.mark.parametrize("shots", [True, 1.5, 0, -3])
def test_run_counts_rejects_a_bad_shot_count(shots: object) -> None:
    circuit = QuantumCircuit(1)

    with pytest.raises(ValueError, match="shots must be a positive integer"):
        CirqCircuitBackend().run_counts(circuit, shots=shots, seed=0)


@pytest.mark.parametrize("seed", [True, "0"])
def test_run_counts_rejects_a_bad_seed(seed: object) -> None:
    circuit = QuantumCircuit(1)

    with pytest.raises(TypeError, match="seed must be an int or None"):
        CirqCircuitBackend().run_counts(circuit, shots=1, seed=seed)


@pytest.mark.parametrize("method", ["depth", "width", "gate_count", "t_count", "toffoli_count"])
def test_circuit_metrics_are_not_supported(method: str) -> None:
    circuit = QuantumCircuit(1)

    with pytest.raises(NotImplementedError, match="circuit metrics"):
        getattr(CirqCircuitBackend(), method)(circuit)


def test_expectations_require_the_cirq_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(module: str, *, extra: str) -> object:
        raise ImportError(f"{module} requires the {extra} extra")

    monkeypatch.setattr("shadowsim.backends.cirq.import_optional", missing)
    circuit = QuantumCircuit(1)
    backend = CirqCircuitBackend()

    with pytest.raises(ImportError, match="cirq"):
        backend.z_expectations(circuit, [0], shots=1, seed=None)
    with pytest.raises(ImportError, match="cirq"):
        backend.x_expectations(circuit, [0], shots=1, seed=None)
    with pytest.raises(ImportError, match="cirq"):
        backend.run_counts(circuit, shots=1, seed=None)
