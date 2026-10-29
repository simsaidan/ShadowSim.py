"""Run shot circuits on Qiskit Aer."""

from collections.abc import Sequence

from qiskit import QuantumCircuit, transpile
from qiskit.circuit import ClassicalRegister
from qiskit_aer import AerSimulator

from shadowsim.backends.circuit import from_qiskit, to_qiskit
from shadowsim.utils.flip_dict import flip_dict


class AerCircuitBackend:
    """Run a circuit on Qiskit Aer and return shot counts.

    A set ``seed`` is passed to ``AerSimulator`` as ``seed_simulator``.
    ``z_expectations`` and ``x_expectations`` estimate Pauli expectations from
    those counts. ``depth``, ``width``, ``gate_count``, ``t_count``, and
    ``toffoli_count`` read the circuit after ``transpile`` for ``AerSimulator``.
    That pass leaves named gates Aer accepts, including ``t``, ``ccx``, and ``ccz``.

    Attributes:
        name: ``"aer"``. Stored on simulation result metadata.
        shots: Shot budget passed to each ``run_counts`` call by a simulator.
    """

    def __init__(self, shots: int = 10000) -> None:
        """Store the shot budget a simulator uses for this backend.

        Args:
            shots: Number of shots for each circuit. Must be a positive integer.

        Raises:
            ValueError: ``shots`` is not a positive integer.
        """
        if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
            raise ValueError("shots must be a positive integer")
        self.name = "aer"
        self.shots = shots

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Rebuild ``circuit`` from its program, transpile that for Aer, and return counts.

        Args:
            circuit: Circuit to execute. It is translated to a program and back
                before transpilation.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            Mapping from bitstring to shot count.

        Raises:
            ValueError: ``circuit`` contains an instruction that has no matrix and
                is not initialize, reset, barrier, or measure.
        """
        native = to_qiskit(from_qiskit(circuit))
        backend = AerSimulator(seed_simulator=seed) if seed is not None else AerSimulator()
        compiled = transpile(native, backend)
        job = backend.run(compiled, shots=shots)
        return job.result().get_counts()

    def z_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Estimate ``⟨Z⟩`` on ``qubits`` from computational-basis shots.

        Args:
            circuit: Circuit to execute, before the computational-basis measurement.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            One estimate per entry of ``qubits``, each ``(n0 - n1) / shots``.

        Raises:
            ValueError: An index is outside ``circuit``, or ``circuit`` contains an
                instruction the program cannot record.
        """
        return _expectations(self, circuit, qubits, shots=shots, seed=seed, basis="z")

    def x_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Estimate ``⟨X⟩`` on ``qubits`` by applying Hadamard and then measuring.

        Args:
            circuit: Circuit to execute, before the X-basis measurement.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            One estimate per entry of ``qubits``, each ``(n0 - n1) / shots``.

        Raises:
            ValueError: An index is outside ``circuit``, or ``circuit`` contains an
                instruction the program cannot record.
        """
        return _expectations(self, circuit, qubits, shots=shots, seed=seed, basis="x")

    def depth(self, circuit: QuantumCircuit) -> int:
        """Return the depth of ``circuit`` after transpilation for Aer.

        Args:
            circuit: Circuit to measure. It is transpiled for ``AerSimulator``.

        Returns:
            Length of the critical path on the transpiled circuit.
        """
        return int(_compiled(circuit).depth())

    def width(self, circuit: QuantumCircuit) -> int:
        """Return the qubit count of ``circuit`` after transpilation for Aer.

        Args:
            circuit: Circuit to measure. It is transpiled for ``AerSimulator``.

        Returns:
            Number of qubits on the transpiled circuit. Classical bits are not included.
        """
        return int(_compiled(circuit).num_qubits)

    def gate_count(self, circuit: QuantumCircuit) -> int:
        """Return the instruction count of ``circuit`` after transpilation for Aer.

        Args:
            circuit: Circuit to measure. It is transpiled for ``AerSimulator``.

        Returns:
            Total number of instructions on the transpiled circuit, including
            measurements when ``circuit`` contains them.
        """
        return int(_compiled(circuit).size())

    def t_count(self, circuit: QuantumCircuit) -> int:
        """Return the number of ``t`` gates after transpilation for Aer.

        ``tdg`` is not included. A multi-qubit unitary stays one instruction, so
        a circuit built only from unitaries reports zero.

        Args:
            circuit: Circuit to measure. It is transpiled for ``AerSimulator``.

        Returns:
            Count of instructions named ``t``.
        """
        return int(_compiled(circuit).count_ops().get("t", 0))

    def toffoli_count(self, circuit: QuantumCircuit) -> int:
        """Return the number of ``ccx`` and ``ccz`` gates after transpilation for Aer.

        A multi-qubit unitary stays one instruction, so a circuit built only
        from unitaries reports zero.

        Args:
            circuit: Circuit to measure. It is transpiled for ``AerSimulator``.

        Returns:
            Sum of ``ccx`` and ``ccz`` instructions.
        """
        counts = _compiled(circuit).count_ops()
        return int(counts.get("ccx", 0)) + int(counts.get("ccz", 0))


def _compiled(circuit: QuantumCircuit) -> QuantumCircuit:
    """Transpile ``circuit`` for Aer, leaving named gates that Aer accepts."""
    return transpile(circuit, AerSimulator())


def _expectations(
    backend: AerCircuitBackend,
    circuit: QuantumCircuit,
    qubits: Sequence[int],
    *,
    shots: int,
    seed: int | None,
    basis: str,
) -> list[float]:
    """Measure ``qubits`` in ``basis`` and return one Pauli expectation per index."""
    indexes = _qubit_indexes(circuit, qubits)
    if not indexes:
        return []
    measured = circuit.copy()
    if basis == "x":
        for index in dict.fromkeys(indexes):
            measured.h(index)
    offset = measured.num_clbits
    measured.add_register(ClassicalRegister(len(indexes)))
    for slot, index in enumerate(indexes):
        measured.measure(index, offset + slot)
    counts = backend.run_counts(measured, shots=shots, seed=seed)
    flipped = flip_dict(counts)
    return [_outcome_difference(flipped, offset + slot) / shots for slot in range(len(indexes))]


def _qubit_indexes(circuit: QuantumCircuit, qubits: Sequence[int]) -> tuple[int, ...]:
    """Return ``qubits`` when every entry is an index in ``circuit``."""
    indexes: list[int] = []
    for qubit in qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= circuit.num_qubits:
            raise ValueError(f"qubit {qubit!r} is outside a circuit of {circuit.num_qubits} qubits")
        indexes.append(qubit)
    return tuple(indexes)


def _outcome_difference(counts: dict[str, int], bit: int) -> int:
    """Return ``n0 - n1`` for classical bit ``bit`` in already-flipped counts."""
    difference = 0
    for bitstring, count in counts.items():
        if bitstring[bit] == "0":
            difference += count
        else:
            difference -= count
    return difference
