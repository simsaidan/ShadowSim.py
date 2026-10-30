"""Agreement checks for the NumPy statevector backend.

Statevector probabilities are compared with Aer at an absolute tolerance of
``1e-8``. Hadamard shot frequencies use 4000 shots. A fair coin at that budget
has a standard deviation near 0.008, so an absolute tolerance of 0.05 leaves
room for ordinary sampling noise and still fails if a sampler collapses to one
outcome. One local Pauli term makes the product formula exact, so Trotterization
with this backend matches ``cos(2t)`` at ``1e-8``. QuTiP's integrator on the same
grid leaves a residual near ``1e-7``, so that comparison uses ``1e-6``.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from shadowsim.backends import AerCircuitBackend, NumpyCircuitBackend
from shadowsim.backends.circuit import from_qiskit
from shadowsim.backends.numpy_statevector import statevector
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, State
from shadowsim.simulators import TrotterizationSimulator

_TOLERANCE = 1e-8
_QUTIP_TOLERANCE = 1e-6
_SHOTS = 4000
_SHOT_TOLERANCE = 0.05
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)


def _numpy_probabilities(circuit: QuantumCircuit) -> np.ndarray:
    """Return Born probabilities from the same translation the backend uses."""
    amplitudes = statevector(from_qiskit(circuit))
    return np.abs(amplitudes) ** 2


def _aer_probabilities(circuit: QuantumCircuit) -> np.ndarray:
    """Return Born probabilities from Aer's statevector method."""
    prepared = circuit.copy()
    prepared.save_statevector()
    result = AerSimulator(method="statevector").run(prepared).result()
    amplitudes = np.asarray(result.get_statevector(), dtype=np.complex128)
    return np.abs(amplitudes) ** 2


def _z_expectations(probabilities: np.ndarray) -> list[float]:
    """Return ``⟨Z⟩`` for every qubit from computational-basis probabilities."""
    indexes = np.arange(probabilities.shape[0])
    num_qubits = int(probabilities.shape[0]).bit_length() - 1
    expectations = []
    for qubit in range(num_qubits):
        signs = np.where((indexes >> qubit) & 1, -1.0, 1.0)
        expectations.append(float(np.dot(probabilities, signs)))
    return expectations


def _circuits() -> list[QuantumCircuit]:
    """Return the small circuits used for the Aer statevector comparison."""
    hadamard = QuantumCircuit(1)
    hadamard.h(0)

    rotation = QuantumCircuit(1)
    rotation.rx(0.4, 0)

    bell = QuantumCircuit(2)
    bell.h(0)
    bell.cx(0, 1)

    prepared = QuantumCircuit(1)
    prepared.initialize([0.0, 1.0], 0)
    prepared.barrier()
    prepared.h(0)

    amplitude = 1.0 / np.sqrt(2.0)
    entangled = QuantumCircuit(2)
    entangled.initialize([amplitude, 0.0, 0.0, amplitude], [0, 1])
    entangled.h(1)
    return [hadamard, rotation, bell, prepared, entangled]


@pytest.mark.parametrize("circuit", _circuits())
def test_probabilities_match_aer_statevector(circuit: QuantumCircuit):
    numpy_probabilities = _numpy_probabilities(circuit)
    aer_probabilities = _aer_probabilities(circuit)

    np.testing.assert_allclose(numpy_probabilities, aer_probabilities, atol=_TOLERANCE, rtol=0)
    qubits = list(range(circuit.num_qubits))
    assert NumpyCircuitBackend().z_expectations(circuit, qubits, shots=1, seed=None) == pytest.approx(
        _z_expectations(aer_probabilities),
        abs=_TOLERANCE,
    )


def test_hadamard_shot_frequencies_agree_with_aer():
    circuit = QuantumCircuit(1, 1)
    circuit.h(0)
    circuit.measure(0, 0)
    numpy_counts = NumpyCircuitBackend().run_counts(circuit, shots=_SHOTS, seed=0)
    aer_counts = AerCircuitBackend().run_counts(circuit, shots=_SHOTS, seed=0)
    numpy_fraction = numpy_counts.get("0", 0) / _SHOTS
    aer_fraction = aer_counts.get("0", 0) / _SHOTS

    assert abs(numpy_fraction - 0.5) < _SHOT_TOLERANCE
    assert abs(aer_fraction - 0.5) < _SHOT_TOLERANCE
    assert abs(numpy_fraction - aer_fraction) < _SHOT_TOLERANCE


def _trotter_x() -> TrotterizationSimulator:
    """Return a one-qubit X evolution whose product formula is exact."""
    return TrotterizationSimulator(
        [LocalHamiltonian(_X, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.5,
        time_steps=5,
        num_steps=3,
        trotter_depth=2,
        circuit_backend=NumpyCircuitBackend(),
    )


def test_trotter_reads_exact_z_expectations():
    result = _trotter_x().simulate()

    assert result.counts is None
    assert result.metadata["circuit_backend"] == "numpy"
    assert result.metadata["observable_kind"] == "qubit_expectations"
    np.testing.assert_allclose(result.observables[0], np.cos(2.0 * result.times), atol=_TOLERANCE, rtol=0)


@pytest.mark.cross_extra
def test_numpy_trotter_matches_qutip_for_one_local_term():
    pytest.importorskip("qutip")
    from shadowsim.simulators import QutipSimulator

    psi0 = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    qutip_result = QutipSimulator(
        [Hamiltonian(_X)],
        [],
        psi0,
        [Operator(_Z)],
        num_qubits=1,
        total_time=0.5,
        time_steps=5,
    ).simulate()
    trotter_result = _trotter_x().simulate()

    np.testing.assert_allclose(
        trotter_result.observables[0],
        qutip_result.observables[0],
        atol=_QUTIP_TOLERANCE,
        rtol=0,
    )
