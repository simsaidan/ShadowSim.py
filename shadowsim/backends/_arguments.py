"""Shared argument checks and circuit-metric rejections for circuit backends."""

from collections.abc import Sequence
from typing import Literal, NoReturn


def _require_shots(shots: object) -> int:
    """Return ``shots`` when it is a positive integer.

    Raises:
        ValueError: ``shots`` is a ``bool``, not an ``int``, or not positive.
    """
    if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
        raise ValueError("shots must be a positive integer")
    return shots


def _require_seed(seed: object) -> int | None:
    """Return ``seed`` when it is an ``int`` or ``None``.

    Raises:
        TypeError: ``seed`` is not an ``int`` or ``None``.
    """
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    return seed


def _qubit_indexes(
    qubits: Sequence[int],
    num_qubits: int,
    *,
    register: Literal["circuit", "program"],
) -> tuple[int, ...]:
    """Return ``qubits`` when every entry is an index in a register of ``num_qubits``.

    Args:
        qubits: Indexes to check. A ``bool`` is rejected.
        num_qubits: Size of the register.
        register: Noun used in the error, ``circuit`` or ``program``.

    Raises:
        ValueError: An entry is outside the register.
    """
    indexes: list[int] = []
    for qubit in qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= num_qubits:
            raise ValueError(f"qubit {qubit!r} is outside a {register} of {num_qubits} qubits")
        indexes.append(qubit)
    return tuple(indexes)


def _reject_circuit_metric(name: str, program: object) -> NoReturn:
    """Raise because the backend named ``name`` does not count gates."""
    del program
    raise NotImplementedError(f"{name} does not support circuit metrics")


class _UnsupportedCircuitMetrics:
    """Reject requests for transpiled circuit metrics.

    Subclasses set ``name`` and inherit the five metric methods. Each method
    raises ``NotImplementedError``.
    """

    name: str

    def depth(self, program: object) -> int:
        """Reject a request for transpiled circuit depth.

        Args:
            program: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(self.name, program)

    def width(self, program: object) -> int:
        """Reject a request for transpiled qubit count.

        Args:
            program: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(self.name, program)

    def gate_count(self, program: object) -> int:
        """Reject a request for a transpiled instruction count.

        Args:
            program: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(self.name, program)

    def t_count(self, program: object) -> int:
        """Reject a request for a transpiled ``t`` count.

        Args:
            program: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(self.name, program)

    def toffoli_count(self, program: object) -> int:
        """Reject a request for a transpiled Toffoli count.

        Args:
            program: Unused. This backend does not count gates.

        Raises:
            NotImplementedError: This backend does not support circuit metrics.
        """
        _reject_circuit_metric(self.name, program)
