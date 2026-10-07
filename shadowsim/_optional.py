"""Import helpers for optional extras."""

import importlib
from types import ModuleType

# Top-level import names provided by each published extra.
_EXTRA_MODULES: dict[str, frozenset[str]] = {
    "qutip": frozenset({"qutip"}),
    "qiskit": frozenset({"qiskit", "qiskit_aer", "scipy"}),
    "viz": frozenset({"matplotlib"}),
}


def import_optional(module: str, *, extra: str) -> ModuleType:
    """Import ``module``, or raise if a library from ``extra`` is not installed.

    Args:
        module: Absolute module name to import.
        extra: Extra that provides the optional library, as in ``shadowsim[extra]``.

    Returns:
        The imported module.

    Raises:
        ImportError: If importing ``module`` fails because a library from
            ``extra`` is missing. The message names the extra and
            ``pip install 'shadowsim[<extra>]'``. Other import failures are
            re-raised unchanged.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        missing = _top_level_name(exc.name)
        if missing is not None and missing in _modules_for_extra(extra):
            raise ImportError(
                f"{module} requires the {extra} extra. Install it with: pip install 'shadowsim[{extra}]'"
            ) from exc
        raise


def _top_level_name(name: str | None) -> str | None:
    """Return the top-level package in an import name."""
    if not name:
        return None
    return name.partition(".")[0]


def _modules_for_extra(extra: str) -> frozenset[str]:
    """Return the top-level modules that ``extra`` is expected to provide."""
    return _EXTRA_MODULES.get(extra, frozenset({extra}))
