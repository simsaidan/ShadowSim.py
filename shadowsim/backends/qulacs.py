"""Run a circuit on the Qulacs statevector simulator.

Qubit 0 is the least significant bit of a gate matrix and of each sample.
Named gates use Qulacs kernels. Every other unitary is a dense matrix.
"""

from collections.abc import Sequence
from typing import Any, Literal, NoReturn

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Instruction
from qiskit.circuit.exceptions import CircuitError

from shadowsim._optional import import_optional

_Pauli = Literal["X", "Z"]

# Method names on ``qulacs.QuantumCircuit``. Qulacs ``RX(θ)``, ``RY(θ)``, and
# ``RZ(θ)`` equal the Qiskit gates of angle ``-θ``, so those three are negated.
_ONE_QUBIT = {
    "h": "add_H_gate",
    "x": "add_X_gate",
    "y": "add_Y_gate",
    "z": "add_Z_gate",
    "s": "add_S_gate",
    "sdg": "add_Sdag_gate",
    "t": "add_T_gate",
    "tdg": "add_Tdag_gate",
    "sx": "add_sqrtX_gate",
    "sxdg": "add_sqrtXdag_gate",
}
_TWO_QUBIT = {
    "cx": "add_CNOT_gate",
    "cz": "add_CZ_gate",
    "swap": "add_SWAP_gate",
}
_ROTATIONS = {
    "rx": "add_RX_gate",
    "ry": "add_RY_gate",
    "rz": "add_RZ_gate",
}


class QulacsCircuitBackend:
    """Evolve one circuit with the Qulacs statevector simulator.

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

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``circuit`` in the computational basis.

        Args:
            circuit: Circuit to execute.
            shots: Number of shots.
            seed: Seed for Qulacs sampling. ``None`` draws without a fixed seed.

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
            ImportError: The ``qulacs`` extra is not installed.
        """
        _check_shots(shots)
        _check_seed(seed)
        state = _state(circuit)
        _check_normalized(state)
        if seed is None:
            outcomes = state.sampling(shots)
        else:
            outcomes = state.sampling(shots, seed)
        counts: dict[str, int] = {}
        width = circuit.num_qubits
        for outcome in outcomes:
            key = format(int(outcome), f"0{width}b")
            counts[key] = counts.get(key, 0) + 1
        return counts

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
            ImportError: The ``qulacs`` extra is not installed.
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
            ImportError: The ``qulacs`` extra is not installed.
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
    qulacs = _qulacs()
    state = _evolve(qulacs, circuit)
    return [_expectation(qulacs, state, circuit.num_qubits, qubit, pauli) for qubit in indexes]


def _state(circuit: QuantumCircuit) -> Any:
    """Return the Qulacs statevector of ``circuit``."""
    return _evolve(_qulacs(), circuit)


def _qulacs() -> Any:
    """Import Qulacs, or raise if the extra is not installed."""
    return import_optional("qulacs", extra="qulacs")


def _evolve(qulacs: Any, circuit: QuantumCircuit) -> Any:
    """Apply ``circuit`` to ``|0...0>`` and return the Qulacs state.

    Args:
        qulacs: Imported Qulacs package.
        circuit: Circuit to apply.

    Returns:
        The evolved ``QuantumState``. Qubit 0 is its least significant bit.

    Raises:
        ValueError: ``circuit`` contains an instruction this backend cannot apply.
        NotImplementedError: ``circuit`` resets a qubit, measures a qubit and
            then applies a gate, or prepares a state after leaving ``|0...0>``.
    """
    state = qulacs.QuantumState(circuit.num_qubits)
    state.set_zero_state()
    compiled = qulacs.QuantumCircuit(circuit.num_qubits)
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
            _flush(compiled, state)
            compiled = qulacs.QuantumCircuit(circuit.num_qubits)
            _prepare(state, operation, qubits)
            continue
        if not _append_named(compiled, operation, qubits):
            _append_matrix(compiled, operation, qubits)
    _flush(compiled, state)
    return state


def _flush(compiled: Any, state: Any) -> None:
    """Apply any gates waiting on ``compiled``."""
    if compiled.get_gate_count() == 0:
        return
    compiled.update_quantum_state(state)


def _prepare(state: Any, operation: Instruction, qubits: tuple[int, ...]) -> None:
    """Write an initialize instruction onto ``state`` while it is ``|0...0>``.

    ``qubits[0]`` is the least significant bit of ``operation.params``.

    Args:
        state: Qulacs state to overwrite.
        operation: Initialize instruction. Its parameters are the amplitudes.
        qubits: Qubits that receive the state, in the amplitude order.

    Raises:
        ValueError: The amplitudes are not one value per basis state of ``qubits``.
        NotImplementedError: ``state`` is not ``|0...0>``.
    """
    vector = np.asarray(state.get_vector(), dtype=np.complex128)
    ground = np.zeros_like(vector)
    ground[0] = 1.0
    if not np.allclose(vector, ground):
        raise NotImplementedError("Prepare after the state has left |0...0> is not supported")
    amplitudes = np.asarray(operation.params, dtype=np.complex128)
    width = 1 << len(qubits)
    if amplitudes.shape != (width,):
        raise ValueError(f"Prepare amplitudes must have shape {(width,)}, got {amplitudes.shape}")
    prepared = np.zeros_like(vector)
    for local, amplitude in enumerate(amplitudes):
        index = 0
        for bit, qubit in enumerate(qubits):
            if local & (1 << bit):
                index |= 1 << qubit
        prepared[index] = amplitude
    state.load(prepared)


def _append_named(compiled: Any, operation: Instruction, qubits: tuple[int, ...]) -> bool:
    """Append ``operation`` when Qulacs has a kernel for it.

    Args:
        compiled: Qulacs circuit that receives the gate.
        operation: Instruction to append.
        qubits: Target indexes. The first is the control of ``cx`` and the
            least significant bit of a one-qubit rotation.

    Returns:
        True when a kernel was appended.
    """
    name = operation.name
    if name in _ONE_QUBIT and len(qubits) == 1:
        getattr(compiled, _ONE_QUBIT[name])(qubits[0])
        return True
    if name in _TWO_QUBIT and len(qubits) == 2:
        getattr(compiled, _TWO_QUBIT[name])(qubits[0], qubits[1])
        return True
    if name in _ROTATIONS and len(qubits) == 1:
        getattr(compiled, _ROTATIONS[name])(qubits[0], -float(operation.params[0]))
        return True
    return False


def _append_matrix(compiled: Any, operation: Instruction, qubits: tuple[int, ...]) -> None:
    """Append ``operation`` as a dense matrix.

    The first entry of ``qubits`` is the least significant bit of the matrix.

    Args:
        compiled: Qulacs circuit that receives the gate.
        operation: Instruction whose matrix is applied.
        qubits: Target indexes, in matrix order.

    Raises:
        ValueError: ``operation`` has no matrix.
    """
    matrix = _matrix(operation)
    if matrix is None:
        raise ValueError(f"unsupported instruction {operation.name!r}")
    compiled.add_dense_matrix_gate(list(qubits), np.asarray(matrix, dtype=np.complex128))


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
    raise NotImplementedError("Qulacs does not support circuit metrics")
