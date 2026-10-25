"""Shared circuit execution for shot-based simulators."""

from typing import Protocol

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Instruction
from qiskit.circuit.exceptions import CircuitError
from qiskit.circuit.library import Initialize, UnitaryGate
from qiskit.providers import BackendV2
from qiskit_aer import AerSimulator

from shadowsim.backends.program import (
    Barrier,
    Hadamard,
    Measure,
    Operation,
    Prepare,
    Program,
    Reset,
    Unitary,
)


class CircuitBackend(Protocol):
    """Execute one circuit and return measurement counts.

    Attributes:
        name: Identifier stored on simulation result metadata.
    """

    name: str

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Run ``circuit`` for ``shots`` and return bitstring counts.

        Args:
            circuit: Circuit to execute. Implementations transpile it for their target.
            shots: Number of shots.
            seed: Optional seed. Implementations use it only when the target accepts one.

        Returns:
            Mapping from bitstring to shot count.
        """
        ...


class AerCircuitBackend:
    """Run a circuit on Qiskit Aer and return shot counts.

    A set ``seed`` is passed to ``AerSimulator`` as ``seed_simulator``.

    Attributes:
        name: ``"aer"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the Aer backend name."""
        self.name = "aer"

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
        native = _rebuilt_circuit(circuit)
        backend = AerSimulator(seed_simulator=seed) if seed is not None else AerSimulator()
        compiled = transpile(native, backend)
        job = backend.run(compiled, shots=shots)
        return job.result().get_counts()


class QiskitCircuitBackend:
    """Run a circuit on a caller-supplied Qiskit ``BackendV2``.

    The wrapped backend is the object that receives ``run``. ``seed`` is accepted
    so this class matches :class:`CircuitBackend` and is not passed as ``seed_simulator``.

    Attributes:
        name: Label stored on simulation result metadata.
    """

    def __init__(self, backend: BackendV2, *, name: str = "qiskit") -> None:
        """Wrap ``backend`` under ``name``.

        Args:
            backend: Qiskit backend that will receive ``run``.
            name: Metadata label. Defaults to ``"qiskit"``.
        """
        self._backend = backend
        self.name = name

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Rebuild ``circuit`` from its program, transpile that, and return counts.

        Args:
            circuit: Circuit to execute. It is translated to a program and back
                before transpilation.
            shots: Number of shots.
            seed: Unused. This backend does not pass ``seed_simulator``.

        Returns:
            Mapping from bitstring to shot count.

        Raises:
            ValueError: ``circuit`` contains an instruction that has no matrix and
                is not initialize, reset, barrier, or measure.
            TypeError: If the run result has no callable ``get_counts``.
        """
        del seed
        native = _rebuilt_circuit(circuit)
        compiled = transpile(native, self._backend)
        job = self._backend.run(compiled, shots=shots)
        result = job.result()
        get_counts = getattr(result, "get_counts", None)
        if not callable(get_counts):
            raise TypeError("backend result does not provide get_counts()")
        return get_counts()


def _rebuilt_circuit(circuit: QuantumCircuit) -> QuantumCircuit:
    """Return ``circuit`` translated to a program and back into Qiskit."""
    return to_qiskit(from_qiskit(circuit))


def from_qiskit(circuit: QuantumCircuit) -> Program:
    """Record the instructions of ``circuit`` as a :class:`Program`.

    Qubit indexes are positions in ``circuit.qubits``. Initialize, Hadamard,
    reset, barrier, and measure are recorded as those operations. Any other
    instruction that provides a matrix, including ``rx`` and a custom unitary,
    is recorded as that matrix on the instruction's qubits.

    Args:
        circuit: Circuit to record.

    Returns:
        The operations on ``circuit``, in order.

    Raises:
        ValueError: An instruction has no matrix and is not initialize, reset,
            barrier, or measure.
    """
    operations: list[Operation] = []
    for instruction in circuit.data:
        qubits = tuple(int(circuit.find_bit(qubit).index) for qubit in instruction.qubits)
        clbits = tuple(int(circuit.find_bit(clbit).index) for clbit in instruction.clbits)
        operations.append(_operation(instruction.operation, qubits, clbits))
    return Program(circuit.num_qubits, circuit.num_clbits, operations)


def to_qiskit(program: Program) -> QuantumCircuit:
    """Build a Qiskit circuit from ``program``.

    The circuit has one quantum register and, when ``program`` has classical
    bits, one classical register. A measurement writes the same qubit onto the
    same classical bit recorded in ``program``.

    Args:
        program: Operations to append.

    Returns:
        A circuit with those operations.
    """
    circuit = QuantumCircuit(program.num_qubits, program.num_clbits)
    for operation in program.operations:
        _append(circuit, operation)
    return circuit


def _operation(operation: Instruction, qubits: tuple[int, ...], clbits: tuple[int, ...]) -> Operation:
    """Translate one Qiskit instruction into a program operation."""
    if isinstance(operation, Initialize):
        return Prepare(_amplitudes(operation), qubits)
    name = operation.name
    if name == "h" and len(qubits) == 1:
        return Hadamard(qubits[0])
    if name == "reset" and len(qubits) == 1:
        return Reset(qubits[0])
    if name == "barrier" and qubits:
        return Barrier(qubits)
    if name == "measure" and len(qubits) == 1 and len(clbits) == 1:
        return Measure(qubits[0], clbits[0])
    matrix = _matrix(operation)
    if matrix is not None:
        return Unitary(matrix, qubits)
    raise ValueError(f"unsupported instruction {name!r}")


def _matrix(operation: Instruction) -> np.ndarray | None:
    """Return the matrix of ``operation`` when the instruction defines one."""
    to_matrix = getattr(operation, "to_matrix", None)
    if not callable(to_matrix):
        return None
    try:
        matrix = np.asarray(to_matrix(), dtype=np.complex128)
    except (AttributeError, CircuitError, TypeError, ValueError):
        return None
    if matrix.ndim != 2:
        return None
    return matrix


def _amplitudes(operation: Initialize) -> np.ndarray:
    """Return the statevector stored on an initialize instruction."""
    return np.asarray(operation.params, dtype=np.complex128)


def _append(circuit: QuantumCircuit, operation: Operation) -> None:
    """Append ``operation`` to ``circuit``."""
    if isinstance(operation, Prepare):
        circuit.initialize(np.array(operation.amplitudes, copy=True), _qubits(circuit, operation.qubits))
        return
    if isinstance(operation, Unitary):
        matrix = np.array(operation.matrix, copy=True)
        circuit.append(UnitaryGate(matrix), _qubits(circuit, operation.qubits))
        return
    if isinstance(operation, Hadamard):
        circuit.h(circuit.qubits[operation.qubit])
        return
    if isinstance(operation, Reset):
        circuit.reset(circuit.qubits[operation.qubit])
        return
    if isinstance(operation, Barrier):
        circuit.barrier(*_qubits(circuit, operation.qubits))
        return
    if isinstance(operation, Measure):
        circuit.measure(circuit.qubits[operation.qubit], circuit.clbits[operation.clbit])
        return
    raise TypeError(f"operations must be circuit operations, got {type(operation).__name__}")


def _qubits(circuit: QuantumCircuit, indexes: tuple[int, ...]) -> list[object]:
    """Return the qubits of ``circuit`` at ``indexes``."""
    return [circuit.qubits[index] for index in indexes]
