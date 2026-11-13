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

pytestmark = [pytest.mark.circuits, pytest.mark.cirq, pytest.mark.cross_extra]

pytest.importorskip("cirq")
pytest.importorskip("scipy")

from backends.agreement_programs import hadamard_counts, programs

from shadowsim.backends.cirq import CirqCircuitBackend, _cirq, _evolve
from shadowsim.backends.numpy import NumpyCircuitBackend
from shadowsim.backends.numpy_statevector import statevector
from shadowsim.backends.program import Program
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import TrotterizationSimulator

_TOLERANCE = 1e-8
_SHOTS = 4000
_SHOT_TOLERANCE = 0.05
_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_IDS = ["hadamard", "rotation", "bell", "prepared", "dense", "named"]


def _cirq_amplitudes(program: Program) -> np.ndarray:
    """Return the statevector from the same evolution the backend uses."""
    return _evolve(_cirq(), program)


@pytest.mark.parametrize("program", programs(), ids=_IDS)
def test_statevectors_match_numpy(program: Program) -> None:
    numpy_amplitudes = statevector(program)
    qubits = list(range(program.num_qubits))
    cirq_backend = CirqCircuitBackend()
    numpy = NumpyCircuitBackend()

    np.testing.assert_allclose(_cirq_amplitudes(program), numpy_amplitudes, atol=_TOLERANCE, rtol=0)
    assert cirq_backend.z_expectations(program, qubits, shots=1, seed=None) == pytest.approx(
        numpy.z_expectations(program, qubits, shots=2, seed=0),
        abs=_TOLERANCE,
    )
    assert cirq_backend.x_expectations(program, qubits, shots=3, seed=1) == pytest.approx(
        numpy.x_expectations(program, qubits, shots=4, seed=None),
        abs=_TOLERANCE,
    )


def test_hadamard_shot_frequencies_agree_with_numpy() -> None:
    program = hadamard_counts()
    cirq_counts = CirqCircuitBackend().run_counts(program, shots=_SHOTS, seed=0)
    numpy_counts = NumpyCircuitBackend().run_counts(program, shots=_SHOTS, seed=1)
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
