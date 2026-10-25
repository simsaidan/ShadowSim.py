"""Circuit program independent of any execution framework."""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt


def _count(value: int, *, label: str) -> int:
    """Return ``value`` when it is a non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer, got {value!r}")
    return value


def _qubit_index(qubit: int, *, label: str) -> int:
    """Return ``qubit`` when it is a non-negative index."""
    if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0:
        raise ValueError(f"{label} qubit must be a non-negative index, got {qubit!r}")
    return qubit


def _qubit_indexes(qubits: Sequence[int], *, label: str) -> tuple[int, ...]:
    """Return ``qubits`` as unique non-negative indexes."""
    chosen: list[int] = []
    for qubit in qubits:
        index = _qubit_index(qubit, label=label)
        if index in chosen:
            raise ValueError(f"{label} qubits must be unique, got a repeated {index}")
        chosen.append(index)
    if not chosen:
        raise ValueError(f"{label} must name at least one qubit")
    return tuple(chosen)


def _complex_array(values: npt.ArrayLike, *, shape: tuple[int, ...], label: str) -> npt.NDArray[np.complex128]:
    """Copy ``values`` into a read-only complex array of ``shape``."""
    try:
        array = np.array(values, dtype=np.complex128, copy=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a complex array of shape {shape}") from exc
    if array.shape != shape:
        raise ValueError(f"{label} must have shape {shape}, got {array.shape}")
    array.setflags(write=False)
    return array


class Prepare:
    """Statevector written onto a set of qubits.

    Attributes:
        amplitudes: Complex amplitudes, one per basis state of ``qubits``.
        qubits: Qubits that receive the state, in the order the amplitudes use.
    """

    amplitudes: npt.NDArray[np.complex128]
    qubits: tuple[int, ...]
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, amplitudes: npt.ArrayLike, qubits: Sequence[int]) -> None:
        """Record ``amplitudes`` on ``qubits``.

        Args:
            amplitudes: One complex amplitude per basis state of ``qubits``.
            qubits: Qubits that receive the state, in the order the amplitudes use.

        Raises:
            ValueError: ``qubits`` is empty, contains a duplicate or a negative index,
                or ``amplitudes`` does not have one entry per basis state.
        """
        self.qubits = _qubit_indexes(qubits, label="Prepare")
        self.amplitudes = _complex_array(
            amplitudes,
            shape=(2 ** len(self.qubits),),
            label="Prepare amplitudes",
        )

    def __eq__(self, other: object) -> bool:
        """Return whether both prepares carry the same qubits and amplitudes."""
        if not isinstance(other, Prepare):
            return NotImplemented
        return self.qubits == other.qubits and bool(np.array_equal(self.amplitudes, other.amplitudes))


class Unitary:
    """Matrix applied to a set of qubits.

    The matrix is stored in the qubit order it was given. It is not transposed.

    Attributes:
        matrix: Square complex matrix of shape ``(2**n, 2**n)`` for ``n`` qubits.
        qubits: Qubits the matrix acts on, in the order ``matrix`` uses.
    """

    matrix: npt.NDArray[np.complex128]
    qubits: tuple[int, ...]
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, matrix: npt.ArrayLike, qubits: Sequence[int]) -> None:
        """Record ``matrix`` on ``qubits``.

        Args:
            matrix: Square matrix whose dimension is ``2 ** len(qubits)``.
            qubits: Qubits the matrix acts on, in the order ``matrix`` uses.

        Raises:
            ValueError: ``qubits`` is empty, contains a duplicate or a negative index,
                or ``matrix`` does not have shape ``(2**n, 2**n)``.
        """
        self.qubits = _qubit_indexes(qubits, label="Unitary")
        dimension = 2 ** len(self.qubits)
        self.matrix = _complex_array(matrix, shape=(dimension, dimension), label="Unitary matrix")

    def __eq__(self, other: object) -> bool:
        """Return whether both unitaries carry the same qubits and matrix."""
        if not isinstance(other, Unitary):
            return NotImplemented
        return self.qubits == other.qubits and bool(np.array_equal(self.matrix, other.matrix))


class Hadamard:
    """Hadamard on one qubit.

    Attributes:
        qubit: Qubit that receives the Hadamard.
    """

    qubit: int
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, qubit: int) -> None:
        """Record a Hadamard on ``qubit``.

        Args:
            qubit: Qubit that receives the Hadamard.

        Raises:
            ValueError: ``qubit`` is not a non-negative index.
        """
        self.qubit = _qubit_index(qubit, label="Hadamard")

    def __eq__(self, other: object) -> bool:
        """Return whether both Hadamards act on the same qubit."""
        if not isinstance(other, Hadamard):
            return NotImplemented
        return self.qubit == other.qubit


class Reset:
    """Return one qubit to the zero state.

    Attributes:
        qubit: Qubit that is reset.
    """

    qubit: int
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, qubit: int) -> None:
        """Record a reset of ``qubit``.

        Args:
            qubit: Qubit that is reset.

        Raises:
            ValueError: ``qubit`` is not a non-negative index.
        """
        self.qubit = _qubit_index(qubit, label="Reset")

    def __eq__(self, other: object) -> bool:
        """Return whether both resets act on the same qubit."""
        if not isinstance(other, Reset):
            return NotImplemented
        return self.qubit == other.qubit


class Barrier:
    """Barrier across one or more qubits.

    Attributes:
        qubits: Qubits the barrier spans.
    """

    qubits: tuple[int, ...]
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, qubits: Sequence[int]) -> None:
        """Record a barrier across ``qubits``.

        Args:
            qubits: Qubits the barrier spans.

        Raises:
            ValueError: ``qubits`` is empty or contains a duplicate or a negative index.
        """
        self.qubits = _qubit_indexes(qubits, label="Barrier")

    def __eq__(self, other: object) -> bool:
        """Return whether both barriers span the same qubits."""
        if not isinstance(other, Barrier):
            return NotImplemented
        return self.qubits == other.qubits


class Measure:
    """Computational-basis measurement of one qubit into one classical bit.

    Attributes:
        qubit: Qubit that is measured.
        clbit: Classical bit that receives the outcome.
    """

    qubit: int
    clbit: int
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, qubit: int, clbit: int) -> None:
        """Record a measurement of ``qubit`` into ``clbit``.

        Args:
            qubit: Qubit that is measured.
            clbit: Classical bit that receives the outcome.

        Raises:
            ValueError: ``qubit`` or ``clbit`` is not a non-negative index.
        """
        self.qubit = _qubit_index(qubit, label="Measure")
        self.clbit = _count(clbit, label="Measure classical bit")

    def __eq__(self, other: object) -> bool:
        """Return whether both measurements use the same qubit and classical bit."""
        if not isinstance(other, Measure):
            return NotImplemented
        return self.qubit == other.qubit and self.clbit == other.clbit


Operation = Prepare | Unitary | Hadamard | Reset | Barrier | Measure


def _bound_qubits(operation: Operation) -> tuple[int, ...]:
    """Return the qubits ``operation`` names."""
    if isinstance(operation, (Hadamard, Reset, Measure)):
        return (operation.qubit,)
    return operation.qubits


class Program:
    """Ordered circuit operations on a fixed register.

    Qubit indexes are positions in that register. An ancilla added before the
    body occupies the lower indexes.

    Attributes:
        num_qubits: Number of qubits in the register.
        num_clbits: Number of classical bits in the register.
        operations: Operations in the order they are applied.
    """

    num_qubits: int
    num_clbits: int
    operations: tuple[Operation, ...]
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, num_qubits: int, num_clbits: int, operations: Sequence[Operation]) -> None:
        """Record ``operations`` on registers of the given sizes.

        Args:
            num_qubits: Number of qubits in the register.
            num_clbits: Number of classical bits in the register.
            operations: Operations in the order they are applied.

        Raises:
            TypeError: An entry of ``operations`` is not a program operation.
            ValueError: A register size is negative, or an operation names a qubit
                or classical bit outside the register.
        """
        self.num_qubits = _count(num_qubits, label="num_qubits")
        self.num_clbits = _count(num_clbits, label="num_clbits")
        recorded: list[Operation] = []
        for operation in operations:
            if not isinstance(operation, (Prepare, Unitary, Hadamard, Reset, Barrier, Measure)):
                raise TypeError(f"operations must be circuit operations, got {type(operation).__name__}")
            self._check_bounds(operation)
            recorded.append(operation)
        self.operations = tuple(recorded)

    def _check_bounds(self, operation: Operation) -> None:
        """Reject a qubit or classical bit outside this program."""
        for qubit in _bound_qubits(operation):
            if qubit >= self.num_qubits:
                raise ValueError(f"qubit {qubit} is outside a program of {self.num_qubits} qubits")
        if isinstance(operation, Measure) and operation.clbit >= self.num_clbits:
            raise ValueError(
                f"classical bit {operation.clbit} is outside a program of {self.num_clbits} classical bits"
            )

    def __eq__(self, other: object) -> bool:
        """Return whether both programs have the same registers and operations."""
        if not isinstance(other, Program):
            return NotImplemented
        return (
            self.num_qubits == other.num_qubits
            and self.num_clbits == other.num_clbits
            and self.operations == other.operations
        )
