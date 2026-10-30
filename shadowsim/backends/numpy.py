"""Run a circuit on a NumPy statevector."""

from collections.abc import Sequence
from typing import Literal, NoReturn

from qiskit import QuantumCircuit

from shadowsim.backends.circuit import from_qiskit
from shadowsim.backends.numpy_statevector import expectations, sample_counts

_Pauli = Literal["X", "Z"]


class NumpyCircuitBackend:
    """Evolve one circuit with a NumPy statevector.

    This is the reference for small circuits. Correctness and readability come
    before performance. ``z_expectations`` and ``x_expectations`` are exact, so
    ``shots`` and ``seed`` are accepted and ignored there. ``run_counts`` samples
    the computational-basis distribution, and the same ``seed`` repeats those
    counts. The backend stores no ``shots`` attribute, so Trotterization reads
    the exact expectations.

    ``Reset``, a measurement followed by a gate, and ``Prepare`` after the
    register has left ``|0...0>`` are rejected. ``depth``, ``width``,
    ``gate_count``, ``t_count``, and ``toffoli_count`` are not available.

    Checked circuits agree with Aer statevector probabilities to an absolute
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

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``circuit`` in the computational basis.

        Args:
            circuit: Circuit to execute. It is translated to a program first.
            shots: Number of shots.
            seed: Seed for the NumPy generator. ``None`` draws without a fixed seed.

        Returns:
            Mapping from bitstring to shot count. The rightmost character is qubit 0.

        Raises:
            ValueError: ``shots`` is not a positive integer, ``circuit`` contains
                an instruction the program cannot record, or the statevector
                probabilities do not sum to 1.
            TypeError: ``seed`` is not an ``int`` or ``None``.
            NotImplementedError: ``circuit`` resets a qubit, or measures a qubit
                and then applies a gate.
        """
        return sample_counts(from_qiskit(circuit), shots=shots, seed=seed)

    def z_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return exact ``⟨Z⟩`` for each qubit in ``qubits``.

        Args:
            circuit: Circuit to execute, before the computational-basis measurement.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``circuit``, or ``circuit`` contains an
                instruction the program cannot record.
            NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
        """
        del shots, seed
        return _expectations(circuit, qubits, "Z")

    def x_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return exact ``⟨X⟩`` for each qubit in ``qubits``.

        Args:
            circuit: Circuit to execute, before the X-basis measurement.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``circuit``, or ``circuit`` contains an
                instruction the program cannot record.
            NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
        """
        del shots, seed
        return _expectations(circuit, qubits, "X")

    def depth(self, circuit: QuantumCircuit) -> int:
        """Reject a request for transpiled circuit depth.

        Args:
            circuit: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(circuit)

    def width(self, circuit: QuantumCircuit) -> int:
        """Reject a request for transpiled qubit count.

        Args:
            circuit: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(circuit)

    def gate_count(self, circuit: QuantumCircuit) -> int:
        """Reject a request for a transpiled instruction count.

        Args:
            circuit: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(circuit)

    def t_count(self, circuit: QuantumCircuit) -> int:
        """Reject a request for a transpiled ``t`` count.

        Args:
            circuit: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(circuit)

    def toffoli_count(self, circuit: QuantumCircuit) -> int:
        """Reject a request for a transpiled Toffoli count.

        Args:
            circuit: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(circuit)


def _expectations(circuit: QuantumCircuit, qubits: Sequence[int], pauli: _Pauli) -> list[float]:
    """Return one exact expectation for each index in ``qubits``."""
    _qubit_indexes(circuit, qubits)
    return expectations(from_qiskit(circuit), qubits, pauli)


def _qubit_indexes(circuit: QuantumCircuit, qubits: Sequence[int]) -> tuple[int, ...]:
    """Return ``qubits`` when every entry is an index in ``circuit``.

    Raises:
        ValueError: An entry is outside ``circuit``.
    """
    indexes: list[int] = []
    for qubit in qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= circuit.num_qubits:
            raise ValueError(f"qubit {qubit!r} is outside a circuit of {circuit.num_qubits} qubits")
        indexes.append(qubit)
    return tuple(indexes)


def _reject_circuit_metric(circuit: QuantumCircuit) -> NoReturn:
    """Raise because this backend does not count gates."""
    del circuit
    raise NotImplementedError("NumPy does not support circuit metrics")
