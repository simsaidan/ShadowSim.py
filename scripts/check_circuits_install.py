"""Run one closed Trotter step on a circuit backend without Qiskit."""

import sys
from collections.abc import Sequence

import numpy as np

from shadowsim.backends.circuit import CircuitBackend
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import TrotterizationSimulator

_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)


def _reject_qiskit() -> None:
    """Exit when this process has imported Qiskit."""
    loaded = [name for name in ("qiskit", "qiskit_aer") if name in sys.modules]
    if loaded:
        raise SystemExit(f"circuits install loaded optional libraries: {loaded}")


def _backend(name: str) -> CircuitBackend:
    """Return the circuit backend named ``name``.

    Args:
        name: ``numpy``, ``qulacs``, or ``cirq``.

    Returns:
        A backend that can run one closed Trotter step.

    Raises:
        SystemExit: ``name`` is not one of those backends.
    """
    if name == "numpy":
        from shadowsim.backends.numpy import NumpyCircuitBackend  # noqa: PLC0415

        return NumpyCircuitBackend()
    if name == "qulacs":
        from shadowsim.backends.qulacs import QulacsCircuitBackend  # noqa: PLC0415

        return QulacsCircuitBackend()
    if name == "cirq":
        from shadowsim.backends.cirq import CirqCircuitBackend  # noqa: PLC0415

        return CirqCircuitBackend()
    raise SystemExit(f"unknown backend {name!r}; expected numpy, qulacs, or cirq")


def main(argv: Sequence[str] | None = None) -> None:
    """Import Trotterization and compare one X evolution with ``cos(2t)``.

    Args:
        argv: Backend name. ``None`` reads it from the command line.

    Raises:
        SystemExit: The command line is wrong, or the process imported Qiskit.
        AssertionError: The Z curve disagrees with ``cos(2t)`` by more than ``1e-8``.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("usage: check_circuits_install.py numpy|qulacs|cirq")
    _reject_qiskit()
    backend = _backend(args[0])
    _reject_qiskit()
    result = TrotterizationSimulator(
        [LocalHamiltonian(_X, [0])],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.5,
        time_steps=2,
        num_steps=1,
        circuit_backend=backend,
    ).simulate()
    _reject_qiskit()
    np.testing.assert_allclose(result.observables[0], np.cos(2.0 * result.times), atol=1e-8, rtol=0)


if __name__ == "__main__":
    main()
