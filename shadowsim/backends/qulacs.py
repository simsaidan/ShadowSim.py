"""Run a program on the Qulacs statevector simulator.

Qubit 0 is the least significant bit of a gate matrix and of each sample.
``Hadamard`` uses the Qulacs kernel. Every ``Unitary`` is a dense matrix.
"""

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


class QulacsCircuitBackend(_UnsupportedCircuitMetrics):
    """Evolve one program with the Qulacs statevector simulator.

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
        name: ``"qulacs"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the Qulacs backend name."""
        self.name = "qulacs"

    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``program`` in the computational basis.

        Args:
            program: Program to execute.
            shots: Number of shots.
            seed: Seed for Qulacs sampling. ``None`` draws without a fixed seed.

        Returns:
            Mapping from bitstring to shot count. The rightmost character is qubit 0.

        Raises:
            ValueError: ``shots`` is not a positive integer, or the statevector
                probabilities do not sum to 1.
            TypeError: ``seed`` is not an ``int`` or ``None``.
            NotImplementedError: ``program`` resets a qubit, measures a qubit
                and then applies a gate, or prepares a state after leaving
                ``|0...0>``.
            ImportError: The ``qulacs`` extra is not installed.
        """
        _require_shots(shots)
        _require_seed(seed)
        state = _state(program)
        _check_normalized(state)
        if seed is None:
            outcomes = state.sampling(shots)
        else:
            outcomes = state.sampling(shots, seed)
        counts: dict[str, int] = {}
        width = program.num_qubits
        for outcome in outcomes:
            key = format(int(outcome), f"0{width}b")
            counts[key] = counts.get(key, 0) + 1
        return counts

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
            ImportError: The ``qulacs`` extra is not installed.
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
            ImportError: The ``qulacs`` extra is not installed.
        """
        del shots, seed
        return _expectations(program, qubits, "X")


def _expectations(program: Program, qubits: Sequence[int], pauli: _Pauli) -> list[float]:
    """Return one exact expectation for each index in ``qubits``."""
    indexes = _qubit_indexes(qubits, program.num_qubits, register="program")
    qulacs = _qulacs()
    state = _evolve(qulacs, program)
    return [_expectation(qulacs, state, program.num_qubits, qubit, pauli) for qubit in indexes]


def _state(program: Program) -> Any:
    """Return the Qulacs statevector of ``program``."""
    return _evolve(_qulacs(), program)


def _qulacs() -> Any:
    """Import Qulacs, or raise if the extra is not installed."""
    return import_optional("qulacs", extra="qulacs")


def _evolve(qulacs: Any, program: Program) -> Any:
    """Apply ``program`` to ``|0...0>`` and return the Qulacs state.

    Args:
        qulacs: Imported Qulacs package.
        program: Program to apply.

    Returns:
        The evolved ``QuantumState``. Qubit 0 is its least significant bit.

    Raises:
        NotImplementedError: ``program`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    state = qulacs.QuantumState(program.num_qubits)
    state.set_zero_state()
    compiled = qulacs.QuantumCircuit(program.num_qubits)
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
            _flush(compiled, state)
            compiled = qulacs.QuantumCircuit(program.num_qubits)
            _prepare(state, operation)
            continue
        if isinstance(operation, Hadamard):
            compiled.add_H_gate(operation.qubit)
            continue
        if isinstance(operation, Unitary):
            compiled.add_dense_matrix_gate(
                list(operation.qubits),
                np.array(operation.matrix, dtype=np.complex128, copy=True),
            )
            continue
        raise TypeError(f"operations must be circuit operations, got {type(operation).__name__}")
    _flush(compiled, state)
    return state


def _flush(compiled: Any, state: Any) -> None:
    """Apply any gates waiting on ``compiled``."""
    if compiled.get_gate_count() == 0:
        return
    compiled.update_quantum_state(state)


def _prepare(state: Any, operation: Prepare) -> None:
    """Write ``operation`` onto ``state`` while it is ``|0...0>``.

    ``operation.qubits[0]`` is the least significant bit of ``operation.amplitudes``.

    Args:
        state: Qulacs state to overwrite.
        operation: State preparation. Its amplitudes are one value per basis state.

    Raises:
        NotImplementedError: ``state`` is not ``|0...0>``.
    """
    vector = np.asarray(state.get_vector(), dtype=np.complex128)
    ground = np.zeros_like(vector)
    ground[0] = 1.0
    if not np.allclose(vector, ground):
        raise NotImplementedError("Prepare after the state has left |0...0> is not supported")
    prepared = np.zeros_like(vector)
    for local, amplitude in enumerate(operation.amplitudes):
        index = 0
        for bit, qubit in enumerate(operation.qubits):
            if local & (1 << bit):
                index |= 1 << qubit
        prepared[index] = amplitude
    state.load(prepared)


def _expectation(qulacs: Any, state: Any, num_qubits: int, qubit: int, pauli: _Pauli) -> float:
    """Return ``⟨pauli⟩`` for ``qubit``."""
    observable = qulacs.Observable(num_qubits)
    observable.add_operator(1.0, f"{pauli} {qubit}")
    return float(observable.get_expectation_value(state))


def _check_normalized(state: Any) -> None:
    """Raise unless the Born weights of ``state`` sum to 1.

    Raises:
        ValueError: The probabilities do not sum to 1.
    """
    if not np.isclose(float(state.get_squared_norm()), 1.0):
        raise ValueError("statevector probabilities must sum to 1")
