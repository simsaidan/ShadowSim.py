"""Run a program on a NumPy statevector."""

from collections.abc import Sequence
from typing import Literal

from shadowsim.backends._arguments import _UnsupportedCircuitMetrics
from shadowsim.backends.numpy_statevector import expectations, sample_counts
from shadowsim.backends.program import Program

_Pauli = Literal["X", "Z"]


class NumpyCircuitBackend(_UnsupportedCircuitMetrics):
    """Evolve one program with a NumPy statevector.

    This is the reference for small programs. Correctness and readability come
    before performance. ``z_expectations`` and ``x_expectations`` are exact, so
    ``shots`` and ``seed`` are accepted and ignored there. ``run_counts`` samples
    the computational-basis distribution, and the same ``seed`` repeats those
    counts. The backend stores no ``shots`` attribute, so Trotterization reads
    the exact expectations.

    ``Reset``, a measurement followed by a gate, and ``Prepare`` after the
    register has left ``|0...0>`` are rejected. ``depth``, ``width``,
    ``gate_count``, ``t_count``, and ``toffoli_count`` are not available.

    Checked programs agree with Aer statevector probabilities to an absolute
    tolerance of ``1e-8``. One local Hamiltonian makes the Trotter product
    exact: that ``⟨Z⟩`` curve matches ``cos(2t)`` to ``1e-8`` and QuTiP to
    ``1e-6``. A seeded Hadamard of 4000 shots stays within ``0.05`` of Aer and
    of ``1/2``.

    Attributes:
        name: ``"numpy"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the NumPy backend name."""
        self.name = "numpy"

    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``program`` in the computational basis.

        Args:
            program: Program to execute.
            shots: Number of shots.
            seed: Seed for the NumPy generator. ``None`` draws without a fixed seed.

        Returns:
            Mapping from bitstring to shot count. The rightmost character is qubit 0.

        Raises:
            ValueError: ``shots`` is not a positive integer, or the statevector
                probabilities do not sum to 1.
            TypeError: ``seed`` is not an ``int`` or ``None``.
            NotImplementedError: ``program`` resets a qubit, or measures a qubit
                and then applies a gate.
        """
        return sample_counts(program, shots=shots, seed=seed)

    def z_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return exact ``⟨Z⟩`` for each qubit in ``qubits``.

        Args:
            program: Program to execute, before the computational-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``program``.
            NotImplementedError: ``program`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
        """
        del shots, seed
        return _expectations(program, qubits, "Z")

    def x_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return exact ``⟨X⟩`` for each qubit in ``qubits``.

        Args:
            program: Program to execute, before the X-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``program``.
            NotImplementedError: ``program`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
        """
        del shots, seed
        return _expectations(program, qubits, "X")


def _expectations(program: Program, qubits: Sequence[int], pauli: _Pauli) -> list[float]:
    """Return one exact expectation for each index in ``qubits``."""
    return expectations(program, qubits, pauli)
