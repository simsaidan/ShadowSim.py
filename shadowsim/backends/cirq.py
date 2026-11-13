"""Run a program on the Cirq statevector simulator.

Qubit 0 is the least significant bit of a gate matrix and of each sample.
``Hadamard`` uses the Cirq kernel. Every ``Unitary`` is a dense matrix.

Cirq treats the first qubit of a matrix, and the first qubit of
``qubit_order``, as the most significant bit. A program matrix is applied on
the reversed qubit list, and the simulated vector is read with qubit 0 as the
least significant bit.
"""

import warnings
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np

from shadowsim._optional import import_optional
from shadowsim.backends._arguments import (
    _qubit_indexes,
    _require_seed,
    _require_shots,
    _UnsupportedCircuitMetrics,
)
from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Reset, Unitary

_Pauli = Literal["X", "Z"]


class CirqCircuitBackend(_UnsupportedCircuitMetrics):
    """Evolve one program with the Cirq statevector simulator.

    ``z_expectations`` and ``x_expectations`` are exact, so ``shots`` and
    ``seed`` are accepted and ignored there. ``run_counts`` samples the
    computational-basis distribution, and the same ``seed`` repeats those
    counts. The backend stores no ``shots`` attribute, so Trotterization reads
    the exact expectations.

    ``Reset``, a measurement followed by a gate, and state preparation after
    the register has left ``|0...0>`` are rejected. ``depth``, ``width``,
    ``gate_count``, ``t_count``, and ``toffoli_count`` are not available.

    Statevectors agree with the NumPy backend to an absolute tolerance of
    ``1e-8``. One local Hamiltonian makes the Trotter product exact: that
    ``⟨Z⟩`` curve matches ``cos(2t)`` to ``1e-8``. A seeded Hadamard of 4000
    shots stays within ``0.05`` of the NumPy frequencies.

    Attributes:
        name: ``"cirq"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the Cirq backend name."""
        self.name = "cirq"

    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``program`` in the computational basis.

        Args:
            program: Program to execute.
            shots: Number of shots.
            seed: Seed for Cirq sampling. ``None`` draws without a fixed seed.

        Returns:
            Mapping from bitstring to shot count. The rightmost character is qubit 0.

        Raises:
            ValueError: ``shots`` is not a positive integer, or the statevector
                probabilities do not sum to 1.
            TypeError: ``seed`` is not an ``int`` or ``None``.
            NotImplementedError: ``program`` resets a qubit, measures a qubit
                and then applies a gate, or prepares a state after leaving
                ``|0...0>``.
            ImportError: The ``cirq`` extra is not installed.
        """
        _require_shots(shots)
        _require_seed(seed)
        state = _state(program)
        return _sample(_cirq(), state, shots=shots, seed=seed)

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
            ImportError: The ``cirq`` extra is not installed.
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
            ImportError: The ``cirq`` extra is not installed.
        """
        del shots, seed
        return _expectations(program, qubits, "X")


def _expectations(program: Program, qubits: Sequence[int], pauli: _Pauli) -> list[float]:
    """Return one exact expectation for each index in ``qubits``."""
    indexes = _qubit_indexes(qubits, program.num_qubits, register="program")
    cirq = _cirq()
    compiled, state, lines = _translate(cirq, program)
    if not indexes:
        return []
    compiled = _register_qubits(cirq, compiled, lines)
    observable = cirq.Z if pauli == "Z" else cirq.X
    values = _simulator(cirq).simulate_expectation_values(
        compiled,
        [observable(lines[qubit]) for qubit in indexes],
        qubit_order=_qubit_order(lines),
        initial_state=np.array(state, dtype=np.complex128, copy=True),
    )
    return [float(np.real(value)) for value in values]


def _state(program: Program) -> np.ndarray:
    """Return the Cirq statevector of ``program``. Qubit 0 is the least significant bit."""
    return _evolve(_cirq(), program)


def _cirq() -> Any:
    """Import Cirq, or raise if the extra is not installed."""
    return import_optional("cirq", extra="cirq")


def _evolve(cirq: Any, program: Program) -> np.ndarray:
    """Apply ``program`` to ``|0...0>`` and return the statevector.

    Args:
        cirq: Imported Cirq package.
        program: Program to apply.

    Returns:
        Complex amplitudes. Qubit 0 is the least significant bit.

    Raises:
        NotImplementedError: ``program`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    compiled, state, lines = _translate(cirq, program)
    if len(compiled) == 0:
        return state
    return _simulate(cirq, compiled, state, lines)


def _translate(cirq: Any, program: Program) -> tuple[Any, np.ndarray, list[Any]]:
    """Translate ``program`` into a Cirq circuit and an initial state.

    Args:
        cirq: Imported Cirq package.
        program: Program to translate.

    Returns:
        The gates that follow the last accepted state preparation, the
        amplitudes those gates start from, and one ``LineQubit`` per program
        qubit. Qubit 0 of the amplitude vector is the least significant bit.

    Raises:
        NotImplementedError: ``program`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    lines = [cirq.LineQubit(index) for index in range(program.num_qubits)]
    compiled = cirq.Circuit()
    state = np.zeros(1 << program.num_qubits, dtype=np.complex128)
    state[0] = 1.0
    measuring = False
    for operation in program.operations:
        if isinstance(operation, Reset):
            raise NotImplementedError("Reset is not supported")
        if isinstance(operation, Measure):
            measuring = True
            continue
        if isinstance(operation, Barrier):
            continue
        if measuring:
            raise NotImplementedError("a measurement before the end of the program is not supported")
        if isinstance(operation, Prepare):
            if len(compiled) != 0:
                state = _simulate(cirq, compiled, state, lines)
                compiled = cirq.Circuit()
            state = _prepare(state, operation)
            continue
        if isinstance(operation, Hadamard):
            compiled.append(cirq.H.on(lines[operation.qubit]))
            continue
        if isinstance(operation, Unitary):
            _append_matrix(cirq, compiled, operation, lines)
            continue
        raise TypeError(f"operations must be circuit operations, got {type(operation).__name__}")
    return compiled, state, lines


def _prepare(state: np.ndarray, operation: Prepare) -> np.ndarray:
    """Return ``operation`` written onto ``state`` while it is ``|0...0>``.

    ``operation.qubits[0]`` is the least significant bit of ``operation.amplitudes``.

    Args:
        state: Amplitudes to overwrite. Qubit 0 is the least significant bit.
        operation: State preparation.

    Returns:
        The prepared amplitudes.

    Raises:
        NotImplementedError: ``state`` is not ``|0...0>``.
    """
    if not _is_ground(state):
        raise NotImplementedError("Prepare after the state has left |0...0> is not supported")
    prepared = np.zeros_like(state)
    for local, amplitude in enumerate(operation.amplitudes):
        index = 0
        for bit, qubit in enumerate(operation.qubits):
            if local & (1 << bit):
                index |= 1 << qubit
        prepared[index] = amplitude
    return prepared


def _append_matrix(cirq: Any, compiled: Any, operation: Unitary, lines: Sequence[Any]) -> None:
    """Append ``operation`` as a dense matrix.

    The first entry of ``operation.qubits`` is the least significant bit of the
    matrix. Cirq's ``MatrixGate`` treats its first qubit as the most significant
    bit, so the gate is applied to the reversed qubit list.

    Args:
        cirq: Imported Cirq package.
        compiled: Cirq circuit that receives the gate.
        operation: Unitary to apply.
        lines: ``LineQubit`` for each program qubit index.
    """
    matrix = np.array(operation.matrix, dtype=np.complex128, copy=True)
    targets = [lines[qubit] for qubit in reversed(operation.qubits)]
    compiled.append(cirq.MatrixGate(matrix).on(*targets))


def _simulate(cirq: Any, compiled: Any, state: np.ndarray, lines: Sequence[Any]) -> np.ndarray:
    """Return the statevector of ``compiled`` starting from ``state``.

    Args:
        cirq: Imported Cirq package.
        compiled: Gates to apply.
        state: Amplitudes ``compiled`` starts from. Qubit 0 is the least
            significant bit.
        lines: ``LineQubit`` for each Qiskit qubit index.

    Returns:
        The evolved amplitudes, in the same order as ``state``.
    """
    registered = _register_qubits(cirq, compiled, lines)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"final state vector's", category=UserWarning)
        result = _simulator(cirq).simulate(
            registered,
            qubit_order=_qubit_order(lines),
            initial_state=np.array(state, dtype=np.complex128, copy=True),
        )
    return np.asarray(result.final_state_vector, dtype=np.complex128)


def _sample(cirq: Any, state: np.ndarray, *, shots: int, seed: int | None) -> dict[str, int]:
    """Sample ``state`` in the computational basis.

    Args:
        cirq: Imported Cirq package.
        state: Amplitudes to sample. Qubit 0 is the least significant bit.
        shots: Number of shots.
        seed: Seed for Cirq's sampler. ``None`` draws without a fixed seed.

    Returns:
        Mapping from bitstring to shot count. The rightmost character is qubit 0.

    Raises:
        ValueError: The probabilities do not sum to 1.
    """
    normalized = _normalized(state)
    n_qubits = normalized.shape[0].bit_length() - 1
    samples = cirq.sample_state_vector(
        _big_endian(normalized),
        list(range(n_qubits)),
        repetitions=shots,
        seed=seed,
    )
    counts: dict[str, int] = {}
    for row in samples:
        key = "".join(str(int(bit)) for bit in reversed(row))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _normalized(state: np.ndarray) -> np.ndarray:
    """Return ``state`` scaled so its Born weights sum to 1.

    Raises:
        ValueError: The probabilities do not sum to 1.
    """
    total = float((np.abs(state) ** 2).sum())
    if not np.isclose(total, 1.0):
        raise ValueError("statevector probabilities must sum to 1")
    return np.asarray(state / np.sqrt(total), dtype=np.complex128)


def _big_endian(state: np.ndarray) -> np.ndarray:
    """Return ``state`` with qubit 0 as the most significant bit.

    ``cirq.sample_state_vector`` reads a statevector in that order. ``state``
    uses Qiskit order, where qubit 0 is the least significant bit.
    """
    n_qubits = state.shape[0].bit_length() - 1
    if n_qubits <= 1:
        return state
    order = tuple(reversed(range(n_qubits)))
    reversed_bits = np.transpose(state.reshape((2,) * n_qubits), order)
    return np.asarray(reversed_bits.reshape(-1), dtype=np.complex128)


def _register_qubits(cirq: Any, compiled: Any, lines: Sequence[Any]) -> Any:
    """Return ``compiled`` with an identity on every qubit it does not mention.

    An untouched qubit still has to be in the circuit. Otherwise Cirq sizes
    the statevector from the gates alone and drops that qubit from the order.

    Args:
        cirq: Imported Cirq package.
        compiled: Circuit to copy when a qubit is missing.
        lines: ``LineQubit`` for each Qiskit qubit index.

    Returns:
        ``compiled``, or a copy that applies identity to the missing qubits.
    """
    missing = [qubit for qubit in lines if qubit not in compiled.all_qubits()]
    if not missing:
        return compiled
    registered = compiled.copy()
    registered.append(cirq.I.on_each(*missing))
    return registered


def _qubit_order(lines: Sequence[Any]) -> list[Any]:
    """Return a Cirq qubit order whose least significant bit is Qiskit qubit 0.

    Cirq treats the first qubit in the order as the most significant bit.
    """
    return list(reversed(lines))


def _simulator(cirq: Any) -> Any:
    """Return a Cirq statevector simulator at ``complex128`` precision.

    Cirq's default ``complex64`` is too coarse for the ``1e-8`` agreement
    with the NumPy statevector.
    """
    return cirq.Simulator(dtype=np.complex128)


def _is_ground(state: np.ndarray) -> bool:
    """Return whether ``state`` is ``|0...0>``."""
    ground = np.zeros_like(state)
    ground[0] = 1.0
    return bool(np.allclose(state, ground))
