"""Execute a circuit program with a NumPy statevector.

Qubit 0 is the least significant bit of the statevector index. Each gate is
applied by moving those qubit axes next to each other and multiplying, which
keeps the update readable on a small register. This is the reference evolution
for small programs. Correctness and readability come before performance.

``Reset``, a measurement followed by a gate, and ``Prepare`` after the register
has left ``|0...0>`` are rejected.
"""

from collections.abc import Sequence
from typing import Literal

import numpy as np
import numpy.typing as npt

from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Reset, Unitary

_Pauli = Literal["X", "Z"]
_BeforeMeasurement = Prepare | Unitary | Hadamard | Barrier
_HADAMARD = np.array([[1.0, 1.0], [1.0, -1.0]], dtype=np.complex128) / np.sqrt(2.0)
_HADAMARD.setflags(write=False)


def statevector(program: Program) -> npt.NDArray[np.complex128]:
    """Return the statevector of ``program`` before its terminal measurement.

    The register starts in ``|0...0>``. ``Prepare`` writes its amplitudes only
    while the register is still in that state. ``Barrier`` is ignored. A
    ``Measure`` may appear only after every gate.

    Args:
        program: Operations to apply.

    Returns:
        Complex amplitudes. Qubit ``q`` is bit ``q`` of the index, so qubit 0 is
        the least significant bit.

    Raises:
        NotImplementedError: ``program`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after the register has
            left ``|0...0>``.
    """
    state = np.zeros(2**program.num_qubits, dtype=np.complex128)
    state[0] = 1.0
    for operation in _before_measurement(program):
        state = _apply(state, operation)
    return state


def expectations(program: Program, qubits: Sequence[int], pauli: _Pauli) -> list[float]:
    """Return the exact expectation of ``pauli`` on each qubit in ``qubits``.

    Args:
        program: Circuit to evolve, before the computational-basis measurement.
        qubits: Qubit indexes. The result follows this order.
        pauli: ``"Z"`` or ``"X"``.

    Returns:
        One expectation per entry of ``qubits``.

    Raises:
        ValueError: ``pauli`` is not ``"X"`` or ``"Z"``, or an index is outside
            ``program``.
        NotImplementedError: ``program`` uses an operation :func:`statevector`
            cannot apply.
    """
    if pauli not in ("X", "Z"):
        raise ValueError("pauli must be 'X' or 'Z'")
    state = statevector(program)
    indexes = _qubit_indexes(qubits, program.num_qubits)
    return [_expectation(state, index, pauli) for index in indexes]


def sample_counts(program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
    """Sample the computational-basis distribution of ``program``.

    A terminal ``Measure`` does not change that distribution. Keys use Qiskit
    order: the rightmost character is qubit 0. The same ``seed`` returns the
    same counts. ``None`` draws without a fixed seed.

    Args:
        program: Circuit to sample.
        shots: Number of shots. Must be a positive integer.
        seed: Seed for ``numpy.random.Generator``, or ``None``.

    Returns:
        Mapping from bitstring to shot count. Outcomes that never occurred are
        omitted.

    Raises:
        ValueError: ``shots`` is not a positive integer, or the statevector
            probabilities do not sum to 1.
        TypeError: ``seed`` is not an ``int`` or ``None``.
        NotImplementedError: ``program`` uses an operation :func:`statevector`
            cannot apply.
    """
    _check_shots(shots)
    _check_seed(seed)
    probabilities = _probabilities(statevector(program))
    outcomes = np.random.default_rng(seed).choice(probabilities.shape[0], size=shots, p=probabilities)
    counts: dict[str, int] = {}
    width = program.num_qubits
    for outcome in outcomes:
        key = format(int(outcome), f"0{width}b")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _before_measurement(program: Program) -> tuple[_BeforeMeasurement, ...]:
    """Return the operations that update the statevector.

    Raises:
        NotImplementedError: ``program`` contains ``Reset``, or a measurement
            followed by a gate.
    """
    kept: list[_BeforeMeasurement] = []
    measuring = False
    for operation in program.operations:
        if isinstance(operation, Reset):
            raise NotImplementedError("Reset is not supported")
        if isinstance(operation, Measure):
            measuring = True
            continue
        if measuring:
            if not isinstance(operation, Barrier):
                raise NotImplementedError("a measurement before the end of the program is not supported")
            continue
        kept.append(operation)
    return tuple(kept)


def _apply(state: npt.NDArray[np.complex128], operation: _BeforeMeasurement) -> npt.NDArray[np.complex128]:
    """Return ``state`` after ``operation``."""
    if isinstance(operation, Prepare):
        return _write_amplitudes(state, operation)
    if isinstance(operation, Unitary):
        return _apply_matrix(state, operation.matrix, operation.qubits)
    if isinstance(operation, Hadamard):
        return _apply_matrix(state, _HADAMARD, (operation.qubit,))
    return state


def _write_amplitudes(state: npt.NDArray[np.complex128], operation: Prepare) -> npt.NDArray[np.complex128]:
    """Write ``operation`` onto ``state`` while the register is ``|0...0>``.

    ``operation.qubits[0]`` is the least significant bit of ``operation.amplitudes``.

    Raises:
        NotImplementedError: ``state`` is not ``|0...0>``.
    """
    ground = np.zeros_like(state)
    ground[0] = 1.0
    if not np.allclose(state, ground):
        raise NotImplementedError("Prepare after the state has left |0...0> is not supported")
    prepared = np.zeros_like(state)
    for local, amplitude in enumerate(operation.amplitudes):
        index = 0
        for bit, qubit in enumerate(operation.qubits):
            if local & (1 << bit):
                index |= 1 << qubit
        prepared[index] = amplitude
    return prepared


def _apply_matrix(
    state: npt.NDArray[np.complex128],
    matrix: npt.NDArray[np.complex128],
    qubits: tuple[int, ...],
) -> npt.NDArray[np.complex128]:
    """Apply ``matrix`` to ``qubits``.

    ``qubits[0]`` is the least significant bit of ``matrix``. The qubit axes
    are moved together, multiplied, and moved back. No ``2^n`` by ``2^n``
    matrix is built.
    """
    num_qubits = state.shape[0].bit_length() - 1
    trailing = [num_qubits - 1 - qubit for qubit in reversed(qubits)]
    leading = [axis for axis in range(num_qubits) if axis not in trailing]
    order = leading + trailing
    moved = np.transpose(state.reshape((2,) * num_qubits), order)
    width = 2 ** len(qubits)
    updated = moved.reshape(-1, width) @ matrix.T
    restored = updated.reshape((2,) * num_qubits)
    inverse = [int(axis) for axis in np.argsort(order)]
    return np.asarray(np.transpose(restored, inverse).reshape(-1), dtype=np.complex128)


def _expectation(state: npt.NDArray[np.complex128], qubit: int, pauli: _Pauli) -> float:
    """Return ``⟨pauli⟩`` for ``qubit``."""
    if pauli == "Z":
        indexes = np.arange(state.shape[0])
        signs = np.where((indexes >> qubit) & 1, -1.0, 1.0)
        return float(np.real(np.vdot(state, state * signs)))
    shift = 1 << qubit
    flipped = state[np.arange(state.shape[0]) ^ shift]
    return float(np.real(np.vdot(state, flipped)))


def _probabilities(state: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
    """Return the Born distribution of ``state``.

    Raises:
        ValueError: The probabilities do not sum to 1.
    """
    weights = np.abs(state) ** 2
    total = float(weights.sum())
    if not np.isclose(total, 1.0):
        raise ValueError("statevector probabilities must sum to 1")
    return np.asarray(weights / total, dtype=np.float64)


def _qubit_indexes(qubits: Sequence[int], num_qubits: int) -> tuple[int, ...]:
    """Return ``qubits`` when every entry is an index in a register of ``num_qubits``.

    Raises:
        ValueError: An entry is not an index in the register.
    """
    indexes: list[int] = []
    for qubit in qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= num_qubits:
            raise ValueError(f"qubit {qubit!r} is outside a program of {num_qubits} qubits")
        indexes.append(qubit)
    return tuple(indexes)


def _check_shots(shots: int) -> None:
    """Raise unless ``shots`` is a positive integer."""
    if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
        raise ValueError("shots must be a positive integer")


def _check_seed(seed: int | None) -> None:
    """Raise unless ``seed`` is an ``int`` or ``None``."""
    if seed is None:
        return
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
