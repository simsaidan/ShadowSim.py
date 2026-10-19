"""Quantum simulator implementations."""

import importlib
from typing import TYPE_CHECKING, Any

from shadowsim._optional import import_optional
from shadowsim.simulators.job import SimulationJob, SimulationStatus
from shadowsim.simulators.reducers import cavity_population, expectation_x, expectation_z, population_one
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator

if TYPE_CHECKING:
    from shadowsim.simulators.qutip_simulator import QutipSimulator as QutipSimulator
    from shadowsim.simulators.splitjmatrix_simulator import SplitJMatrixSimulator as SplitJMatrixSimulator
    from shadowsim.simulators.trotterization_simulator import TrotterizationSimulator as TrotterizationSimulator

# Simulators loaded on first access: name -> (module, extra).
# extra is None when the simulator has no optional dependency.
_EXPORTS: dict[str, tuple[str, str | None]] = {
    "QutipSimulator": ("shadowsim.simulators.qutip_simulator", "qutip"),
    "SplitJMatrixSimulator": ("shadowsim.simulators.splitjmatrix_simulator", "qiskit"),
    "TrotterizationSimulator": ("shadowsim.simulators.trotterization_simulator", "qiskit"),
}

__all__ = [
    "QutipSimulator",
    "SimulationJob",
    "SimulationResult",
    "SimulationStatus",
    "Simulator",
    "SplitJMatrixSimulator",
    "TrotterizationSimulator",
    "cavity_population",
    "expectation_x",
    "expectation_z",
    "population_one",
]


def __getattr__(name: str) -> Any:
    """Import an optional simulator the first time it is accessed."""
    try:
        module_name, extra = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    if extra is None:
        module = importlib.import_module(module_name)
    else:
        module = import_optional(module_name, extra=extra)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes, including simulators that have not been imported yet."""
    return sorted(set(globals()) | set(_EXPORTS))
