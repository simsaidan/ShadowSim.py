"""Circuit execution backends for shot-based simulators."""

import importlib
from typing import TYPE_CHECKING, Any

from shadowsim._optional import import_optional

if TYPE_CHECKING:
    from shadowsim.backends.aer import AerCircuitBackend as AerCircuitBackend
    from shadowsim.backends.circuit import CircuitBackend as CircuitBackend
    from shadowsim.backends.circuit import from_qiskit as from_qiskit
    from shadowsim.backends.circuit import to_qiskit as to_qiskit
    from shadowsim.backends.cirq import CirqCircuitBackend as CirqCircuitBackend
    from shadowsim.backends.numpy import NumpyCircuitBackend as NumpyCircuitBackend
    from shadowsim.backends.pauli_propagation import PauliPropagationBackend as PauliPropagationBackend
    from shadowsim.backends.qulacs import QulacsCircuitBackend as QulacsCircuitBackend

# ``CircuitBackend`` does not import Qiskit. ``from_qiskit`` and ``to_qiskit`` share
# that module, so the loader checks for Qiskit before returning those two names.
_QISKIT_TRANSLATION = frozenset({"from_qiskit", "to_qiskit"})
_EXPORTS: dict[str, tuple[str, str | None]] = {
    "AerCircuitBackend": ("shadowsim.backends.aer", "qiskit"),
    "NumpyCircuitBackend": ("shadowsim.backends.numpy", None),
    "QulacsCircuitBackend": ("shadowsim.backends.qulacs", "qulacs"),
    "CirqCircuitBackend": ("shadowsim.backends.cirq", "cirq"),
    "CircuitBackend": ("shadowsim.backends.circuit", None),
    "PauliPropagationBackend": ("shadowsim.backends.pauli_propagation", "pauli_propagation"),
    "from_qiskit": ("shadowsim.backends.circuit", "qiskit"),
    "to_qiskit": ("shadowsim.backends.circuit", "qiskit"),
}

# Imported after ``_EXPORTS`` so the catalog can read that map while this module loads.
from shadowsim.backends.catalog import ListedBackend as ListedBackend
from shadowsim.backends.catalog import listed_backends as listed_backends

__all__ = [
    "AerCircuitBackend",
    "CircuitBackend",
    "CirqCircuitBackend",
    "ListedBackend",
    "NumpyCircuitBackend",
    "PauliPropagationBackend",
    "QulacsCircuitBackend",
    "from_qiskit",
    "listed_backends",
    "to_qiskit",
]


def __getattr__(name: str) -> Any:
    """Import a circuit backend the first time it is accessed."""
    try:
        module_name, extra = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    if name in _QISKIT_TRANSLATION:
        import_optional("qiskit", extra="qiskit")
    if extra is None:
        module = importlib.import_module(module_name)
    else:
        module = import_optional(module_name, extra=extra)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes, including backends that have not been imported yet."""
    return sorted(set(globals()) | set(_EXPORTS))
