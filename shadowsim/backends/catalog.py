"""List the concrete circuit backends for the builder page."""

import inspect
import math
from types import ModuleType
from typing import NotRequired, TypedDict

from shadowsim._optional import import_optional
from shadowsim.backends import _EXPORTS

_FIELD_LABELS = {
    "basis_gates": "Gates",
    "max_weight": "Max weight",
    "min_abs_coeff": "Min coefficient",
}


class ListedField(TypedDict):
    """One constructor setting the builder page can edit."""

    name: str
    label: str
    default: str
    allow_inf: bool
    kind: NotRequired[str]
    choices: NotRequired[list[str]]


class ListedBackend(TypedDict):
    """Display record for one concrete circuit backend."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str
    shots: bool
    fields: list[ListedField]


def listed_backends() -> list[ListedBackend]:
    """Return the concrete circuit backends in export order.

    Each exported backend module is imported on its own. A missing extra skips
    that module. ``CircuitBackend`` is a protocol, so it is omitted. Each
    record uses the class name and the first line of its docstring. Required
    constructor arguments appear in ``setup``. A ``shots`` parameter is written
    as ``{shots}`` so the page can fill the shot budget. ``basis_gates``, when
    its default is ``None``, is a gate list written as ``{basis_gates}``. Its
    choices are the class attribute ``BASIS_GATE_NAMES``. Any other parameter
    with a default is a numeric field the page can edit, written as ``{name}``.

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
        arguments, fields = _backend_arguments(value, parameters)
        listed.append(
            {
                "id": title.lower(),
                "title": title,
                "detail": detail,
                "phrase": title,
                "setup": f"circuit_backend = {value.__name__}({', '.join(arguments)})",
                "shots": any(parameter.name == "shots" for parameter in parameters),
                "fields": fields,
            }
        )
    return listed


def _backend_arguments(owner: type, parameters: list[inspect.Parameter]) -> tuple[list[str], list[ListedField]]:
    """Return setup arguments and the editable fields among ``parameters``."""
    arguments: list[str] = []
    fields: list[ListedField] = []
    for parameter in parameters:
        if parameter.name == "shots":
            arguments.append("shots={shots}")
            continue
        if parameter.name == "basis_gates" and parameter.default is None:
            arguments.append("basis_gates={basis_gates}")
            fields.append(_gate_field(owner))
            continue
        if parameter.default is inspect.Parameter.empty:
            arguments.append(parameter.name)
            continue
        arguments.append(f"{parameter.name}={{{parameter.name}}}")
        default = parameter.default
        fields.append(
            {
                "name": parameter.name,
                "label": _FIELD_LABELS.get(parameter.name, parameter.name),
                "default": "inf" if isinstance(default, float) and math.isinf(default) else format(default, ".12g"),
                "allow_inf": isinstance(default, float) and math.isinf(default),
            }
        )
    return arguments, fields


def _gate_field(owner: type) -> ListedField:
    """Return the gate-list field published by ``owner``."""
    published = getattr(owner, "BASIS_GATE_NAMES", ())
    choices = [name for name in published if isinstance(name, str)]
    return {
        "name": "basis_gates",
        "label": _FIELD_LABELS["basis_gates"],
        "default": "",
        "allow_inf": False,
        "kind": "gates",
        "choices": choices,
    }
