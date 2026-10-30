"""Run a circuit on the Cirq statevector simulator.

Qubit 0 is the least significant bit of a gate matrix and of each sample.
Named gates use Cirq kernels. Every other unitary is a dense matrix.

Cirq treats the first qubit of a matrix, and the first qubit of
``qubit_order``, as the most significant bit. A Qiskit matrix is applied on
the reversed qubit list, and the simulated vector is read with qubit 0 as the
least significant bit. Cirq rotations use the same sign as Qiskit.
"""

import warnings
from collections.abc import Sequence
from typing import Any, Literal, NoReturn

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Instruction
from qiskit.circuit.exceptions import CircuitError

from shadowsim._optional import import_optional

_Pauli = Literal["X", "Z"]
_ONE_QUBIT = frozenset({"h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg"})
_TWO_QUBIT = frozenset({"cz", "swap"})
_ROTATIONS = frozenset({"rx", "ry", "rz"})


class CirqCircuitBackend:
    """Evolve one circuit with the Cirq statevector simulator.

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

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``circuit`` in the computational basis.

        Args:
            circuit: Circuit to execute.
            shots: Number of shots.
            seed: Seed for Cirq sampling. ``None`` draws without a fixed seed.

        Returns:
            Mapping from bitstring to shot count. The rightmost character is qubit 0.

        Raises:
            ValueError: ``shots`` is not a positive integer, ``circuit`` contains
                an instruction this backend cannot apply, or the statevector
                probabilities do not sum to 1.
            TypeError: ``seed`` is not an ``int`` or ``None``.
            NotImplementedError: ``circuit`` resets a qubit, measures a qubit
                and then applies a gate, or prepares a state after leaving
                ``|0...0>``.
            ImportError: The ``cirq`` extra is not installed.
        """
        _check_shots(shots)
        _check_seed(seed)
        state = _state(circuit)
        return _sample(_cirq(), state, shots=shots, seed=seed)

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
                instruction this backend cannot apply.
            NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
            ImportError: The ``cirq`` extra is not installed.
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
                instruction this backend cannot apply.
            NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
                then applies a gate, or prepares a state after leaving ``|0...0>``.
            ImportError: The ``cirq`` extra is not installed.
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
    indexes = _qubit_indexes(circuit, qubits)
    cirq = _cirq()
    compiled, state, lines = _translate(cirq, circuit)
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


def _state(circuit: QuantumCircuit) -> np.ndarray:
    """Return the Cirq statevector of ``circuit`` in Qiskit order."""
    return _evolve(_cirq(), circuit)


def _cirq() -> Any:
    """Import Cirq, or raise if the extra is not installed."""
    return import_optional("cirq", extra="cirq")


def _evolve(cirq: Any, circuit: QuantumCircuit) -> np.ndarray:
    """Apply ``circuit`` to ``|0...0>`` and return the statevector.

    Args:
        cirq: Imported Cirq package.
        circuit: Circuit to apply.

    Returns:
        Complex amplitudes. Qubit 0 is the least significant bit.

    Raises:
        ValueError: ``circuit`` contains an instruction this backend cannot apply.
        NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    compiled, state, lines = _translate(cirq, circuit)
    if len(compiled) == 0:
        return state
    return _simulate(cirq, compiled, state, lines)


def _translate(cirq: Any, circuit: QuantumCircuit) -> tuple[Any, np.ndarray, list[Any]]:
    """Translate ``circuit`` into a Cirq circuit and a Qiskit-ordered initial state.

    Args:
        cirq: Imported Cirq package.
        circuit: Circuit to translate.

    Returns:
        The gates that follow the last accepted state preparation, the
        amplitudes those gates start from, and one ``LineQubit`` per Qiskit
        qubit. Qubit 0 of the amplitude vector is the least significant bit.

    Raises:
        ValueError: ``circuit`` contains an instruction this backend cannot apply.
        NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    lines = [cirq.LineQubit(index) for index in range(circuit.num_qubits)]
    compiled = cirq.Circuit()
    state = np.zeros(1 << circuit.num_qubits, dtype=np.complex128)
    state[0] = 1.0
    measuring = False
    for instruction in circuit.data:
        operation = instruction.operation
        qubits = tuple(int(circuit.find_bit(qubit).index) for qubit in instruction.qubits)
        if operation.name == "reset":
            raise NotImplementedError("Reset is not supported")
        if operation.name == "measure":
            measuring = True
            continue
        if operation.name == "barrier":
            continue
        if measuring:
            raise NotImplementedError("a measurement before the end of the program is not supported")
        if operation.name == "initialize":
            if len(compiled) != 0:
                state = _simulate(cirq, compiled, state, lines)
                compiled = cirq.Circuit()
            state = _prepare(state, operation, qubits)
            continue
        named = _named_operation(cirq, operation, qubits, lines)
        if named is not None:
            compiled.append(named)
            continue
        _append_matrix(cirq, compiled, operation, qubits, lines)
    return compiled, state, lines


def _prepare(state: np.ndarray, operation: Instruction, qubits: tuple[int, ...]) -> np.ndarray:
    """Return ``operation`` written onto ``state`` while it is ``|0...0>``.

    ``qubits[0]`` is the least significant bit of ``operation.params``.

    Args:
        state: Amplitudes to overwrite. Qubit 0 is the least significant bit.
        operation: Initialize instruction. Its parameters are the amplitudes.
        qubits: Qubits that receive the state, in the amplitude order.

    Returns:
        The prepared amplitudes.

    Raises:
        ValueError: The amplitudes are not one value per basis state of ``qubits``.
        NotImplementedError: ``state`` is not ``|0...0>``.
    """
    if not _is_ground(state):
        raise NotImplementedError("Prepare after the state has left |0...0> is not supported")
    amplitudes = np.asarray(operation.params, dtype=np.complex128)
    width = 1 << len(qubits)
    if amplitudes.shape != (width,):
        raise ValueError(f"Prepare amplitudes must have shape {(width,)}, got {amplitudes.shape}")
    prepared = np.zeros_like(state)
    for local, amplitude in enumerate(amplitudes):
        index = 0
        for bit, qubit in enumerate(qubits):
            if local & (1 << bit):
                index |= 1 << qubit
        prepared[index] = amplitude
    return prepared


def _named_operation(
    cirq: Any,
    operation: Instruction,
    qubits: tuple[int, ...],
    lines: Sequence[Any],
) -> Any | None:
    """Return a Cirq kernel for ``operation``, or None when none fits.

    Args:
        cirq: Imported Cirq package.
        operation: Instruction to translate.
        qubits: Target indexes. The first is the control of ``cx``.
        lines: ``LineQubit`` for each Qiskit qubit index.

    Returns:
        The Cirq operation, or None when the name or qubit count does not match
        a kernel.
    """
    name = operation.name
    if name in _ONE_QUBIT and len(qubits) == 1:
        return _one_qubit_gate(cirq, name).on(lines[qubits[0]])
    if name == "cx" and len(qubits) == 2:
        return cirq.CNOT(lines[qubits[0]], lines[qubits[1]])
    if name in _TWO_QUBIT and len(qubits) == 2:
        return getattr(cirq, name.upper())(lines[qubits[0]], lines[qubits[1]])
    if name in _ROTATIONS and len(qubits) == 1 and len(operation.params) == 1:
        try:
            angle = float(operation.params[0])
        except (TypeError, ValueError):
            return None
        return getattr(cirq, name)(angle).on(lines[qubits[0]])
    return None


def _one_qubit_gate(cirq: Any, name: str) -> Any:
    """Return the Cirq gate named ``name``."""
    if name == "sdg":
        return cirq.S**-1
    if name == "tdg":
        return cirq.T**-1
    if name == "sx":
        return cirq.X**0.5
    if name == "sxdg":
        return cirq.X**-0.5
    return getattr(cirq, name.upper())


def _append_matrix(
    cirq: Any,
    compiled: Any,
    operation: Instruction,
    qubits: tuple[int, ...],
    lines: Sequence[Any],
) -> None:
    """Append ``operation`` as a dense matrix.

    The first entry of ``qubits`` is the least significant bit of the Qiskit
    matrix. Cirq's ``MatrixGate`` treats its first qubit as the most
    significant bit, so the gate is applied to the reversed qubit list.

    Args:
        cirq: Imported Cirq package.
        compiled: Cirq circuit that receives the gate.
        operation: Instruction whose matrix is applied.
        qubits: Target indexes, in Qiskit matrix order.
        lines: ``LineQubit`` for each Qiskit qubit index.

    Raises:
        ValueError: ``operation`` has no square matrix of the right width.
    """
    matrix = _matrix(operation)
    width = 1 << len(qubits)
    if matrix is None or matrix.shape != (width, width):
        raise ValueError(f"unsupported instruction {operation.name!r}")
    targets = [lines[qubit] for qubit in reversed(qubits)]
    compiled.append(cirq.MatrixGate(matrix).on(*targets))


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
    if not lines:
        return compiled
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


def _reject_circuit_metric(circuit: QuantumCircuit) -> NoReturn:
    """Raise because this backend does not count gates."""
    del circuit
    raise NotImplementedError("Cirq does not support circuit metrics")
