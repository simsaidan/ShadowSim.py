"""Tests for the Qulacs circuit backend."""

import numpy as np
import pytest

pytestmark = pytest.mark.qulacs

pytest.importorskip("qulacs")

from shadowsim import backends
from shadowsim.backends.program import Hadamard, Measure, Prepare, Program, Reset, Unitary
from shadowsim.backends.qulacs import QulacsCircuitBackend

_RX = np.array(
    [
        [np.cos(0.2), -1j * np.sin(0.2)],
        [-1j * np.sin(0.2), np.cos(0.2)],
    ],
    dtype=np.complex128,
)
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def test_qulacs_backend_is_exported() -> None:
    backend = QulacsCircuitBackend()

    assert backends.QulacsCircuitBackend is QulacsCircuitBackend
    assert "QulacsCircuitBackend" in dir(backends)
    assert backend.name == "qulacs"
    assert not hasattr(backend, "shots")


def test_expectations_are_exact_and_ignore_shots_and_seed() -> None:
    program = Program(1, 0, [Unitary(_RX, [0])])
    backend = QulacsCircuitBackend()

    assert backend.z_expectations(program, [0], shots=1, seed=0) == pytest.approx([np.cos(0.4)])
    assert backend.z_expectations(program, [0], shots=99, seed=1) == pytest.approx([np.cos(0.4)])
    assert backend.x_expectations(program, [0], shots=3, seed=None) == pytest.approx([0.0])
    assert backend.z_expectations(program, [], shots=1, seed=None) == []


def test_run_counts_uses_qiskit_bit_order_and_the_seed() -> None:
    hadamard = Program(1, 1, [Hadamard(0), Measure(0, 0)])
    excited = Program(2, 0, [Unitary(_X, [1])])
    backend = QulacsCircuitBackend()

    first = backend.run_counts(hadamard, shots=20, seed=0)
    assert first == backend.run_counts(hadamard, shots=20, seed=0)
    assert set(first) <= {"0", "1"}
    assert sum(first.values()) == 20
    assert backend.run_counts(excited, shots=2, seed=0) == {"10": 2}
    unseeded = backend.run_counts(excited, shots=3, seed=None)
    assert unseeded == {"10": 3}


def test_reset_and_a_mid_circuit_measure_are_rejected() -> None:
    reset = Program(1, 0, [Reset(0)])
    measured = Program(1, 1, [Measure(0, 0), Hadamard(0)])
    backend = QulacsCircuitBackend()

    with pytest.raises(NotImplementedError, match="Reset is not supported"):
        backend.z_expectations(reset, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="measurement before the end"):
        backend.run_counts(measured, shots=1, seed=0)


def test_prepare_after_a_gate_is_rejected() -> None:
    moved = Program(1, 0, [Hadamard(0), Prepare([0.0, 1.0], [0])])

    with pytest.raises(NotImplementedError, match="Prepare after the state has left"):
        QulacsCircuitBackend().z_expectations(moved, [0], shots=1, seed=None)


def test_run_counts_rejects_a_state_whose_probabilities_do_not_sum_to_one() -> None:
    program = Program(1, 0, [Prepare([0.0, 0.0], [0])])

    with pytest.raises(ValueError, match="probabilities must sum to 1"):
        QulacsCircuitBackend().run_counts(program, shots=1, seed=0)


@pytest.mark.parametrize("qubit", [True, 1.5, -1, 1])
def test_expectations_reject_a_bad_qubit_index(qubit: object) -> None:
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="outside a program of 1 qubits"):
        QulacsCircuitBackend().x_expectations(program, [qubit], shots=1, seed=None)


@pytest.mark.parametrize("shots", [True, 1.5, 0, -3])
def test_run_counts_rejects_a_bad_shot_count(shots: object) -> None:
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="shots must be a positive integer"):
        QulacsCircuitBackend().run_counts(program, shots=shots, seed=0)


@pytest.mark.parametrize("seed", [True, "0"])
def test_run_counts_rejects_a_bad_seed(seed: object) -> None:
    program = Program(1, 0, [])

    with pytest.raises(TypeError, match="seed must be an int or None"):
        QulacsCircuitBackend().run_counts(program, shots=1, seed=seed)


@pytest.mark.parametrize("method", ["depth", "width", "gate_count", "t_count", "toffoli_count"])
def test_circuit_metrics_are_not_supported(method: str) -> None:
    program = Program(1, 0, [])

    with pytest.raises(NotImplementedError, match="circuit metrics"):
        getattr(QulacsCircuitBackend(), method)(program)


def test_an_unknown_operation_is_rejected() -> None:
    program = Program(1, 0, [])
    program.operations = (object(),)  # type: ignore[assignment]

    with pytest.raises(TypeError, match="circuit operations"):
        QulacsCircuitBackend().run_counts(program, shots=1, seed=0)


def test_expectations_require_the_qulacs_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(module: str, *, extra: str) -> object:
        raise ImportError(f"{module} requires the {extra} extra")

    monkeypatch.setattr("shadowsim.backends.qulacs.import_optional", missing)
    program = Program(1, 0, [])
    backend = QulacsCircuitBackend()

    with pytest.raises(ImportError, match="qulacs"):
        backend.z_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(ImportError, match="qulacs"):
        backend.x_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(ImportError, match="qulacs"):
        backend.run_counts(program, shots=1, seed=None)
