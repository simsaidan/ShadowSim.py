"""Agreement checks for the Cirq statevector backend.

Amplitudes are compared with the NumPy statevector at an absolute tolerance
of ``1e-8``, so the Born probabilities agree at that tolerance too. Hadamard
shot frequencies use 4000 shots. A fair coin at that budget has a standard
deviation near 0.008, so an absolute tolerance of 0.05 leaves room for
ordinary sampling noise and still fails if a sampler collapses to one outcome.
One local Pauli term makes the product formula exact, so Trotterization with
this backend matches ``cos(2t)`` at ``1e-8``.
"""

import numpy as np
import pytest

pytestmark = [pytest.mark.qiskit, pytest.mark.cirq, pytest.mark.cross_extra]

pytest.importorskip("qiskit")
pytest.importorskip("cirq")
pytest.importorskip("scipy")

from qiskit import QuantumCircuit
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.circuit import from_qiskit
from shadowsim.backends.cirq import CirqCircuitBackend, _cirq, _evolve
from shadowsim.backends.numpy import NumpyCircuitBackend
from shadowsim.backends.numpy_statevector import statevector
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import TrotterizationSimulator

_TOLERANCE = 1e-8
_SHOTS = 4000
_SHOT_TOLERANCE = 0.05
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def _cirq_amplitudes(circuit: QuantumCircuit) -> np.ndarray:
    """Return the statevector from the same evolution the backend uses."""
    return _evolve(_cirq(), circuit)


def _circuits() -> list[QuantumCircuit]:
    """Return the small circuits used for the NumPy statevector comparison."""
    hadamard = QuantumCircuit(1)
    hadamard.h(0)

    rotation = QuantumCircuit(1)
    rotation.rx(0.4, 0)
    rotation.s(0)

    bell = QuantumCircuit(2)
    bell.h(0)
    bell.cx(0, 1)

    amplitude = np.sqrt(1.0 - 0.01 - 0.09 - 0.04)
    prepared = QuantumCircuit(2)
    prepared.initialize([0.1, 0.3, 0.2, amplitude], [1, 0])
    prepared.barrier()
    prepared.h(0)

    raw = np.random.default_rng(0).normal(size=(4, 4)) + 1j * np.random.default_rng(1).normal(size=(4, 4))
    unitary, _ = np.linalg.qr(raw)
    dense = QuantumCircuit(2)
    dense.append(UnitaryGate(unitary), [1, 0])

    named = QuantumCircuit(2)
    named.h(0)
    named.x(1)
    named.y(0)
    named.z(1)
    named.s(0)
    named.sdg(1)
    named.t(0)
    named.tdg(1)
    named.sx(0)
    named.sxdg(1)
    named.cx(0, 1)
    named.cz(1, 0)
    named.swap(0, 1)
    named.rx(0.3, 0)
    named.ry(-0.2, 1)
    named.rz(0.5, 0)
    return [hadamard, rotation, bell, prepared, dense, named]


@pytest.mark.parametrize("circuit", _circuits())
def test_statevectors_match_numpy(circuit: QuantumCircuit) -> None:
    numpy_amplitudes = statevector(from_qiskit(circuit))
    qubits = list(range(circuit.num_qubits))
    cirq_backend = CirqCircuitBackend()
    numpy = NumpyCircuitBackend()

    np.testing.assert_allclose(_cirq_amplitudes(circuit), numpy_amplitudes, atol=_TOLERANCE, rtol=0)
    assert cirq_backend.z_expectations(circuit, qubits, shots=1, seed=None) == pytest.approx(
        numpy.z_expectations(circuit, qubits, shots=2, seed=0),
        abs=_TOLERANCE,
    )
    assert cirq_backend.x_expectations(circuit, qubits, shots=3, seed=1) == pytest.approx(
        numpy.x_expectations(circuit, qubits, shots=4, seed=None),
        abs=_TOLERANCE,
    )


def test_hadamard_shot_frequencies_agree_with_numpy() -> None:
    circuit = QuantumCircuit(1, 1)
    circuit.h(0)
    circuit.measure(0, 0)
    cirq_counts = CirqCircuitBackend().run_counts(circuit, shots=_SHOTS, seed=0)
    numpy_counts = NumpyCircuitBackend().run_counts(circuit, shots=_SHOTS, seed=1)
    cirq_fraction = cirq_counts.get("0", 0) / _SHOTS
    numpy_fraction = numpy_counts.get("0", 0) / _SHOTS

    assert abs(cirq_fraction - 0.5) < _SHOT_TOLERANCE
    assert abs(numpy_fraction - 0.5) < _SHOT_TOLERANCE
    assert abs(cirq_fraction - numpy_fraction) < _SHOT_TOLERANCE


def test_trotter_reads_exact_z_expectations() -> None:
    result = TrotterizationSimulator(
        [LocalHamiltonian(_X, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.5,
        time_steps=5,
        num_steps=3,
        trotter_depth=2,
        circuit_backend=CirqCircuitBackend(),
    ).simulate()

    assert result.counts is None
    assert result.metadata["circuit_backend"] == "cirq"
    assert result.metadata["observable_kind"] == "qubit_expectations"
    np.testing.assert_allclose(result.observables[0], np.cos(2.0 * result.times), atol=_TOLERANCE, rtol=0)
