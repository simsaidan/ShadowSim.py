"""Tests for the NumPy circuit backend."""

import numpy as np
import pytest

from shadowsim import backends
from shadowsim.backends.numpy import NumpyCircuitBackend
from shadowsim.backends.program import Hadamard, Measure, Program, Reset, Unitary

_RX = np.array(
    [
        [np.cos(0.2), -1j * np.sin(0.2)],
        [-1j * np.sin(0.2), np.cos(0.2)],
    ],
    dtype=np.complex128,
)
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def test_numpy_backend_is_exported():
    backend = NumpyCircuitBackend()

    assert backends.NumpyCircuitBackend is NumpyCircuitBackend
    assert "NumpyCircuitBackend" in dir(backends)
    assert backend.name == "numpy"
    assert not hasattr(backend, "shots")


def test_expectations_are_exact_and_ignore_shots_and_seed():
    program = Program(1, 0, [Unitary(_RX, [0])])
    backend = NumpyCircuitBackend()

    assert backend.z_expectations(program, [0], shots=1, seed=0) == pytest.approx([np.cos(0.4)])
    assert backend.z_expectations(program, [0], shots=99, seed=1) == pytest.approx([np.cos(0.4)])
    assert backend.x_expectations(program, [0], shots=3, seed=None) == pytest.approx([0.0])
    assert backend.z_expectations(program, [], shots=1, seed=None) == []


def test_run_counts_uses_qiskit_bit_order_and_the_seed():
    hadamard = Program(1, 1, [Hadamard(0), Measure(0, 0)])
    excited = Program(2, 0, [Unitary(_X, [1])])
    backend = NumpyCircuitBackend()

    assert backend.run_counts(hadamard, shots=20, seed=0) == {"1": 12, "0": 8}
    assert backend.run_counts(hadamard, shots=20, seed=0) == backend.run_counts(hadamard, shots=20, seed=0)
    assert backend.run_counts(excited, shots=1, seed=0) == {"10": 1}


def test_reset_and_a_mid_circuit_measure_are_rejected():
    reset = Program(1, 0, [Reset(0)])
    measured = Program(1, 1, [Measure(0, 0), Hadamard(0)])
    backend = NumpyCircuitBackend()

    with pytest.raises(NotImplementedError, match="Reset is not supported"):
        backend.z_expectations(reset, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="measurement before the end"):
        backend.run_counts(measured, shots=1, seed=0)


@pytest.mark.parametrize("qubit", [True, 1.5, -1, 1])
def test_expectations_reject_a_bad_qubit_index(qubit):
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="outside a program of 1 qubits"):
        NumpyCircuitBackend().x_expectations(program, [qubit], shots=1, seed=None)


@pytest.mark.parametrize("method", ["depth", "width", "gate_count", "t_count", "toffoli_count"])
def test_circuit_metrics_are_not_supported(method: str):
    program = Program(1, 0, [])

    with pytest.raises(NotImplementedError, match="circuit metrics"):
        getattr(NumpyCircuitBackend(), method)(program)
