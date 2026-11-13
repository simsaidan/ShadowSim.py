"""Verify a core install imports without optional extras."""

import sys

import numpy as np

from shadowsim import backends, interop, simulators
from shadowsim.backends import circuit
from shadowsim.core import Hamiltonian, State
from shadowsim.models import ising, jaynes_cummings, tavis_cummings
from shadowsim.shadow import ShadowHamiltonian


def _expect_extra(action, extra: str) -> None:
    """Run ``action`` and require an ImportError that names ``extra``."""
    try:
        action()
    except ImportError as exc:
        hint = f"shadowsim[{extra}]"
        if hint not in str(exc):
            raise SystemExit(f"expected {hint} in ImportError, got: {exc}") from exc
    else:
        raise SystemExit(f"expected ImportError for the {extra} extra")


def _plot() -> None:
    """Call a plot method so a missing viz extra is reported."""
    simulator = simulators.Simulator(
        [Hamiltonian("Z")],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        num_qubits=1,
        total_time=0.1,
        time_steps=2,
        id="core-check",
    )
    # A result has to exist first; otherwise the missing-run check fires
    # before the matplotlib import this script is here to require.
    simulator.results = [[0.0, 1.0]]
    simulator.plot_results()


def main() -> None:
    """Import the core API, then require hints for missing extras."""
    for obj in (Hamiltonian, ShadowHamiltonian, ising, jaynes_cummings, tavis_cummings, interop, simulators.Simulator):
        if obj is None:
            raise SystemExit("core import returned None")
    if backends.CircuitBackend is not circuit.CircuitBackend:
        raise SystemExit("CircuitBackend export does not match the protocol")

    loaded = [name for name in ("qutip", "qiskit", "qiskit_aer", "scipy", "matplotlib") if name in sys.modules]
    if loaded:
        raise SystemExit(f"core import loaded optional libraries: {loaded}")

    _expect_extra(lambda: simulators.QutipSimulator, "qutip")
    _expect_extra(lambda: interop.from_qutip, "qutip")
    _expect_extra(lambda: simulators.HybridWMLSimulator, "circuits")
    _expect_extra(lambda: simulators.SplitJMatrixSimulator, "circuits")
    _expect_extra(lambda: simulators.TrotterizationSimulator, "circuits")
    _expect_extra(lambda: backends.from_qiskit, "qiskit")
    _expect_extra(lambda: backends.to_qiskit, "qiskit")
    _expect_extra(_plot, "viz")


if __name__ == "__main__":
    main()
