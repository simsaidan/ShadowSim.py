"""Circuit backend protocol and Qiskit program translation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

import numpy as np

from shadowsim._optional import import_optional
from shadowsim.backends._arguments import _require_shots
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

if TYPE_CHECKING:
    from qiskit import QuantumCircuit
    from qiskit.circuit import Instruction


class CircuitBackend(Protocol):
    """Execute one program and return shot counts or Pauli expectations.

    Attributes:
        name: Identifier stored on simulation result metadata.
    """

    name: str

    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Run ``program`` for ``shots`` and return bitstring counts.

        Args:
            program: Program to execute. Implementations compile it for their target.
            shots: Number of shots.
            seed: Optional seed. Implementations use it only when the target accepts one.

        Returns:
            Mapping from bitstring to shot count.
        """
        ...

    def z_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return ``⟨Z⟩`` for each qubit in ``qubits``.

        Args:
            program: Program to execute, before the computational-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Number of shots used when the backend estimates from counts.
            seed: Optional seed. Implementations use it only when the target accepts one.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``program``.
        """
        ...

    def x_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return ``⟨X⟩`` for each qubit in ``qubits``.

        Args:
            program: Program to execute, before the X-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Number of shots used when the backend estimates from counts.
            seed: Optional seed. Implementations use it only when the target accepts one.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``program``.
        """
        ...

    def depth(self, program: Program) -> int:
        """Return the depth of ``program`` after compilation for this backend.

        Args:
            program: Program to measure. Implementations compile it for their target.

        Returns:
            Length of the critical path on the compiled circuit.

        Raises:
            NotImplementedError: This backend does not expose gate counts.
        """
        ...

    def width(self, program: Program) -> int:
        """Return the number of qubits on ``program`` after compilation.

        Args:
            program: Program to measure. Implementations compile it for their target.

        Returns:
            Qubit count of the compiled circuit. Classical bits are not included.

        Raises:
            NotImplementedError: This backend does not expose gate counts.
        """
        ...

    def gate_count(self, program: Program) -> int:
        """Return the instruction count of ``program`` after compilation.

        Args:
            program: Program to measure. Implementations compile it for their target.

        Returns:
            Total number of instructions on the compiled circuit, including
            measurements when ``program`` contains them.

        Raises:
            NotImplementedError: This backend does not expose gate counts.
        """
        ...

    def t_count(self, program: Program) -> int:
        """Return the number of ``t`` gates on ``program`` after compilation.

        ``tdg`` is not included.

        Args:
            program: Program to measure. Implementations compile it for their target.

        Returns:
            Count of instructions named ``t``.

        Raises:
            NotImplementedError: This backend does not expose gate counts.
        """
        ...

    def toffoli_count(self, program: Program) -> int:
        """Return the number of Toffoli gates on ``program`` after compilation.

        A Toffoli is ``ccx`` or ``ccz``.

        Args:
            program: Program to measure. Implementations compile it for their target.

        Returns:
            Sum of ``ccx`` and ``ccz`` instructions.

        Raises:
            NotImplementedError: This backend does not expose gate counts.
        """
        ...


def backend_samples(backend: object) -> bool:
    """Return whether ``backend`` stores a shot budget.

    Args:
        backend: Circuit backend. Sampling backends store ``shots``.

    Returns:
        True when ``backend`` has a ``shots`` attribute.
    """
    return hasattr(backend, "shots")


def backend_shots(backend: object) -> int:
    """Return the positive shot count stored on ``backend``.

    Args:
        backend: Sampling backend. It must store ``shots`` as a positive integer.

    Returns:
        That shot count.

    Raises:
        ValueError: ``shots`` is missing or not a positive integer.
    """
    return _require_shots(getattr(backend, "shots", None))


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
        ImportError: Qiskit is not installed.
        ValueError: An instruction has no matrix and is not initialize, reset,
            barrier, or measure.
    """
    import_optional("qiskit", extra="qiskit")
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

    Raises:
        ImportError: Qiskit is not installed.
    """
    qiskit = import_optional("qiskit", extra="qiskit")
    circuit = qiskit.QuantumCircuit(program.num_qubits, program.num_clbits)
    for operation in program.operations:
        _append(circuit, operation)
    return circuit


def _operation(operation: Instruction, qubits: tuple[int, ...], clbits: tuple[int, ...]) -> Operation:
    """Translate one Qiskit instruction into a program operation."""
    library = import_optional("qiskit.circuit.library", extra="qiskit")
    if isinstance(operation, library.Initialize):
        return Prepare(np.asarray(operation.params, dtype=np.complex128), qubits)
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
    exceptions = import_optional("qiskit.circuit.exceptions", extra="qiskit")
    to_matrix = getattr(operation, "to_matrix", None)
    if not callable(to_matrix):
        return None
    try:
        matrix = np.asarray(to_matrix(), dtype=np.complex128)
    except (AttributeError, exceptions.CircuitError, TypeError, ValueError):
        return None
    if matrix.ndim != 2:
        return None
    return matrix


def _append(circuit: QuantumCircuit, operation: Operation) -> None:
    """Append ``operation`` to ``circuit``."""
    library = import_optional("qiskit.circuit.library", extra="qiskit")
    if isinstance(operation, Prepare):
        circuit.initialize(np.array(operation.amplitudes, copy=True), _qubits(circuit, operation.qubits))
        return
    if isinstance(operation, Unitary):
        matrix = np.array(operation.matrix, copy=True)
        circuit.append(library.UnitaryGate(matrix), _qubits(circuit, operation.qubits))
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
