"""Verify a core install imports without optional extras."""

import sys

import numpy as np

from shadowsim import simulators
from shadowsim.core import Hamiltonian, State
from shadowsim.models import tavis_cummings
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
        1,
        0.1,
        2,
        "core-check",
    )
    simulator.plot_results()


def main() -> None:
    """Import the core API, then require hints for missing extras."""
    for obj in (Hamiltonian, ShadowHamiltonian, tavis_cummings, simulators.Simulator):
        if obj is None:
            raise SystemExit("core import returned None")

    loaded = [name for name in ("qutip", "qiskit", "qiskit_aer", "scipy", "matplotlib") if name in sys.modules]
    if loaded:
        raise SystemExit(f"core import loaded optional libraries: {loaded}")

    _expect_extra(lambda: simulators.QutipSimulator, "qutip")
    _expect_extra(lambda: simulators.SplitJMatrixSimulator, "qiskit")
    _expect_extra(_plot, "viz")


if __name__ == "__main__":
    main()
