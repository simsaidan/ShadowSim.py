"""List the concrete circuit backends for the builder page."""

import inspect
from types import ModuleType
from typing import TypedDict

from shadowsim._optional import import_optional
from shadowsim.backends import _EXPORTS


class ListedBackend(TypedDict):
    """Display record for one concrete circuit backend."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str
    shots: bool


def listed_backends() -> list[ListedBackend]:
    """Return the concrete circuit backends in export order.

    Each exported backend module is imported on its own. A missing extra skips
    that module. ``CircuitBackend`` is a protocol, so it is omitted. Each
    record uses the class name and the first line of its docstring. Required
    constructor arguments appear in ``setup``. A ``shots`` parameter is written
    as ``{shots}`` so the page can fill the shot budget.

    Returns:
        Backends the builder page can offer.

    Raises:
        ImportError: No circuit backend module could be imported. The first
            failure is re-raised.
    """
    listed: list[ListedBackend] = []
    first_error: ImportError | None = None
    seen: set[str] = set()
    for module_name, extra in _EXPORTS.values():
        if module_name in seen:
            continue
        seen.add(module_name)
        try:
            module = import_optional(module_name, extra=extra)
        except ImportError as exc:
            if first_error is None:
                first_error = exc
            continue
        listed.extend(_describe_backends(module))
    if listed:
        return listed
    if first_error is not None:
        raise first_error
    raise ImportError("no circuit backends could be imported")


def _describe_backends(module: ModuleType) -> list[ListedBackend]:
    """Describe concrete backend classes defined on ``module``."""
    listed: list[ListedBackend] = []
    for value in vars(module).values():
        if not isinstance(value, type) or value.__module__ != module.__name__:
            continue
        if getattr(value, "_is_protocol", False) or not callable(getattr(value, "run_counts", None)):
            continue
        title = value.__name__.removesuffix("CircuitBackend").removesuffix("Backend")
        document = inspect.getdoc(value)
        detail = title if document is None else document.split("\n", 1)[0].replace("``", "")
        parameters = list(inspect.signature(value).parameters.values())
        arguments = [
            "shots={shots}" if parameter.name == "shots" else parameter.name
            for parameter in parameters
            if parameter.name == "shots" or parameter.default is inspect.Parameter.empty
        ]
        listed.append(
            {
                "id": title.lower(),
                "title": title,
                "detail": detail,
                "phrase": title,
                "setup": f"circuit_backend = {value.__name__}({', '.join(arguments)})",
                "shots": any(parameter.name == "shots" for parameter in parameters),
            }
        )
    return listed
