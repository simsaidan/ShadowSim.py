"""Interop helpers for optional external libraries."""

from shadowsim._optional import import_optional

_EXPORTS: dict[str, tuple[str, str]] = {
    "from_qutip": ("shadowsim.interop.qutip", "qutip"),
    "to_qutip": ("shadowsim.interop.qutip", "qutip"),
}

__all__ = [
    "from_qutip",
    "to_qutip",
]


def __getattr__(name: str):
    """Import a QuTiP interop helper the first time it is accessed."""
    try:
        module_name, extra = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_optional(module_name, extra=extra)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes, including helpers that have not been imported yet."""
    return sorted(set(globals()) | set(_EXPORTS))
