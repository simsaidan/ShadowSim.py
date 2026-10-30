"""Tests for the NumPy circuit backend."""

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")

from qiskit import QuantumCircuit

from shadowsim import backends
from shadowsim.backends.numpy import NumpyCircuitBackend


def test_numpy_backend_is_exported():
    backend = NumpyCircuitBackend()

    assert backends.NumpyCircuitBackend is NumpyCircuitBackend
    assert "NumpyCircuitBackend" in dir(backends)
    assert backend.name == "numpy"
    assert not hasattr(backend, "shots")


def test_expectations_are_exact_and_ignore_shots_and_seed():
    circuit = QuantumCircuit(1)
    circuit.rx(0.4, 0)
    backend = NumpyCircuitBackend()

    assert backend.z_expectations(circuit, [0], shots=1, seed=0) == pytest.approx([np.cos(0.4)])
    assert backend.z_expectations(circuit, [0], shots=99, seed=1) == pytest.approx([np.cos(0.4)])
    assert backend.x_expectations(circuit, [0], shots=3, seed=None) == pytest.approx([0.0])
    assert backend.z_expectations(circuit, [], shots=1, seed=None) == []


def test_run_counts_uses_qiskit_bit_order_and_the_seed():
    hadamard = QuantumCircuit(1, 1)
    hadamard.h(0)
    hadamard.measure(0, 0)
    excited = QuantumCircuit(2)
    excited.x(1)
    backend = NumpyCircuitBackend()

    assert backend.run_counts(hadamard, shots=20, seed=0) == {"1": 12, "0": 8}
    assert backend.run_counts(hadamard, shots=20, seed=0) == backend.run_counts(hadamard, shots=20, seed=0)
    assert backend.run_counts(excited, shots=1, seed=0) == {"10": 1}


def test_reset_and_a_mid_circuit_measure_are_rejected():
    reset = QuantumCircuit(1)
    reset.reset(0)
    measured = QuantumCircuit(1, 1)
    measured.measure(0, 0)
    measured.h(0)
    backend = NumpyCircuitBackend()

    with pytest.raises(NotImplementedError, match="Reset is not supported"):
        backend.z_expectations(reset, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="measurement before the end"):
        backend.run_counts(measured, shots=1, seed=0)


@pytest.mark.parametrize("qubit", [True, 1.5, -1, 1])
def test_expectations_reject_a_bad_qubit_index(qubit):
    circuit = QuantumCircuit(1)

    with pytest.raises(ValueError, match="outside a circuit of 1 qubits"):
        NumpyCircuitBackend().x_expectations(circuit, [qubit], shots=1, seed=None)


@pytest.mark.parametrize("method", ["depth", "width", "gate_count", "t_count", "toffoli_count"])
def test_circuit_metrics_are_not_supported(method: str):
    circuit = QuantumCircuit(1)

    with pytest.raises(NotImplementedError, match="circuit metrics"):
        getattr(NumpyCircuitBackend(), method)(circuit)
