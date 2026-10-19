"""List the concrete circuit backends for the builder page."""

import inspect
from types import ModuleType
from typing import TypedDict

from shadowsim._optional import import_optional


class ListedBackend(TypedDict):
    """Display record for one concrete circuit backend."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str


def listed_backends() -> list[ListedBackend]:
    """Return the concrete circuit backends in definition order.

    ``CircuitBackend`` is a protocol, so it is omitted. ``QiskitCircuitBackend``
    needs a caller-supplied backend, so the page does not offer it. Each record
    uses the class name, the first line of its docstring, and its required
    constructor arguments.

    Returns:
        Backends the builder page can offer.

    Raises:
        ImportError: The Qiskit extra is not installed.
    """
    module = import_optional("shadowsim.backends.circuit", extra="qiskit")
    return _describe_backends(module)


def _describe_backends(module: ModuleType) -> list[ListedBackend]:
    """Describe concrete backend classes defined on ``module``."""
    listed: list[ListedBackend] = []
    for value in vars(module).values():
        if not isinstance(value, type) or value.__module__ != module.__name__:
            continue
        if getattr(value, "_is_protocol", False) or not callable(getattr(value, "run_counts", None)):
            continue
        if value.__name__ == "QiskitCircuitBackend":
            continue
        title = value.__name__.removesuffix("CircuitBackend")
        document = inspect.getdoc(value)
        detail = title if document is None else document.split("\n", 1)[0].replace("``", "")
        required = [
            parameter.name
            for parameter in inspect.signature(value).parameters.values()
            if parameter.default is inspect.Parameter.empty
        ]
        listed.append(
            {
                "id": title.lower(),
                "title": title,
                "detail": detail,
                "phrase": title,
                "setup": f"circuit_backend = {value.__name__}({', '.join(required)})",
            }
        )
    return listed
