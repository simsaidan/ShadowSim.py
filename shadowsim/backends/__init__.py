"""Circuit execution backends for shot-based simulators."""

from typing import TYPE_CHECKING, Any

from shadowsim._optional import import_optional
from shadowsim.backends.catalog import ListedBackend as ListedBackend
from shadowsim.backends.catalog import listed_backends as listed_backends

if TYPE_CHECKING:
    from shadowsim.backends.circuit import AerCircuitBackend as AerCircuitBackend
    from shadowsim.backends.circuit import CircuitBackend as CircuitBackend
    from shadowsim.backends.circuit import QiskitCircuitBackend as QiskitCircuitBackend
    from shadowsim.backends.circuit import from_qiskit as from_qiskit
    from shadowsim.backends.circuit import to_qiskit as to_qiskit

_EXPORTS: dict[str, tuple[str, str]] = {
    "AerCircuitBackend": ("shadowsim.backends.circuit", "qiskit"),
    "CircuitBackend": ("shadowsim.backends.circuit", "qiskit"),
    "QiskitCircuitBackend": ("shadowsim.backends.circuit", "qiskit"),
    "from_qiskit": ("shadowsim.backends.circuit", "qiskit"),
    "to_qiskit": ("shadowsim.backends.circuit", "qiskit"),
}

__all__ = [
    "AerCircuitBackend",
    "CircuitBackend",
    "ListedBackend",
    "QiskitCircuitBackend",
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
    module = import_optional(module_name, extra=extra)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes, including backends that have not been imported yet."""
    return sorted(set(globals()) | set(_EXPORTS))
