"""List the concrete simulators for the builder page."""

import importlib
import inspect
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, get_args, get_origin

from shadowsim import simulators
from shadowsim._optional import import_optional
from shadowsim.simulators.simulator import Simulator

# Chip parameters, in no particular order. A constructor that does not take one
# does not publish it. ``time_steps`` uses ``observables_default`` when the
# constructor records observables. ``use_constructor_default`` keeps an integer
# default from the signature; the others use the page budget below.
_TIME_STEPS = "time_steps"
_NUM_STEPS = "num_steps"
_TROTTER_DEPTH = "trotter_depth"
_ORDER = "order"
_SEED = "seed"


@dataclass(frozen=True)
class _ChipField:
    """How one constructor parameter appears on the simulator card."""

    label: str
    kind: Literal["integer", "choice"]
    default: str
    minimum: int | None = None
    maximum: int | None = None
    observables_default: str | None = None
    use_constructor_default: bool = False


_CHIP_FIELDS: dict[str, _ChipField] = {
    _TIME_STEPS: _ChipField("Time steps", "integer", "11", minimum=1, maximum=500, observables_default="101"),
    _NUM_STEPS: _ChipField("Product steps", "integer", "4", minimum=1, maximum=100),
    _TROTTER_DEPTH: _ChipField("Trotter depth", "integer", "1", minimum=1, maximum=100, use_constructor_default=True),
    _ORDER: _ChipField("Order", "choice", "1", use_constructor_default=True),
    _SEED: _ChipField("Seed", "integer", "0"),
}

# Constructor parameters the page fills. ``basis`` is glued onto the previous
# argument so an empty measurement leaves that argument unchanged.
_STRUCTURAL: dict[str, str] = {
    "hamiltonians": "{hamiltonians}",
    "lindblads": "{lindblads}",
    "initial_state": "state",
    "observables": "e_ops",
    "num_qubits": "num_qubits={qubits}",
    "total_time": "total_time={total}",
    "circuit_backend": "circuit_backend={backend}",
}


class ListedSimulatorField(TypedDict):
    """One constructor setting the builder page can edit.

    ``choices`` is present when ``kind`` is ``choice``. ``minimum`` and
    ``maximum`` are present when the integer is bounded. ``default`` is the
    text that fills the chip. A missing posted value uses that default.
    """

    name: str
    label: str
    kind: Literal["integer", "choice"]
    default: str
    choices: NotRequired[list[str]]
    minimum: NotRequired[int]
    maximum: NotRequired[int]


class ListedSimulator(TypedDict):
    """Display record for one concrete simulator."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str
    observables: bool
    samples: bool
    closed_system: bool
    fields: list[ListedSimulatorField]


def listed_simulators() -> list[ListedSimulator]:
    """Return the exported simulator classes whose modules import successfully.

    :class:`~shadowsim.simulators.simulator.Simulator` itself is omitted. A class
    is skipped when its extra is not installed. ``observables`` is true when the
    constructor takes ``observables``, so the page uses the explicit-operator
    path. ``samples`` is true when the class sets ``requires_sampling_backend``,
    so the page pairs it only with a backend that has a shot budget.
    ``closed_system`` is true when the class sets that attribute. ``title`` and
    ``phrase`` are the class ``title`` attribute. A class without one uses its
    name with ``Simulator`` removed.

    ``fields`` lists the chip parameters that constructor takes, in signature
    order. The names are ``time_steps``, ``num_steps``, ``trotter_depth``,
    ``order``, and ``seed``. A parameter the constructor does not take is
    absent. ``time_steps`` defaults to 101 when the constructor records
    observables and 11 otherwise. ``num_steps`` defaults to 4 and ``seed`` to
    0. ``trotter_depth`` and ``order`` use the constructor default. A bounded
    integer carries ``minimum`` and ``maximum``. ``order`` is a choice taken
    from its ``Literal`` annotation.

    ``setup`` names the class and walks the constructor. The page's values stay
    as placeholders: ``{name}``, ``{hamiltonians}``, ``{lindblads}``, ``state``,
    ``e_ops``, ``{qubits}``, ``{total}``, and ``{backend}``. ``{basis}`` is
    glued to the argument before ``basis``. Each chip parameter is written
    ``{name}``. An optional parameter that is not a chip is omitted. A required
    parameter the page does not fill is left as its name.

    Returns:
        Simulators the builder page can offer.

    Raises:
        ImportError: None of the simulator modules could be imported.
    """
    listed: list[ListedSimulator] = []
    for class_name, (module_name, extra) in simulators._EXPORTS.items():
        try:
            module = (
                importlib.import_module(module_name) if extra is None else import_optional(module_name, extra=extra)
            )
        except ImportError:
            continue
        value = getattr(module, class_name, None)
        if not isinstance(value, type) or not issubclass(value, Simulator) or value is Simulator:
            continue
        listed.append(_describe_simulator(value))
    if not listed:
        raise ImportError("no simulators could be imported")
    return listed


def _chip_default(name: str, *, observables: bool = False) -> str:
    """Return the page default for the chip parameter ``name``.

    Args:
        name: A key of :data:`_CHIP_FIELDS`.
        observables: Use the observables default when that parameter has one.
    """
    spec = _CHIP_FIELDS[name]
    if observables and spec.observables_default is not None:
        return spec.observables_default
    return spec.default


def _chip_maximum(name: str) -> int:
    """Return the inclusive upper bound for the chip parameter ``name``.

    Args:
        name: A key of :data:`_CHIP_FIELDS` whose spec sets ``maximum``.

    Raises:
        KeyError: ``name`` is not a bounded chip parameter.
    """
    maximum = _CHIP_FIELDS[name].maximum
    if maximum is None:
        raise KeyError(name)
    return maximum


def _catalog_title(cls: type, stem: str) -> str:
    """Return the board title for ``cls``.

    A class ``title`` is that string. Otherwise ``stem`` is the class name with
    ``Simulator`` removed, so a simulator that does not set ``title`` still lists.
    """
    title = getattr(cls, "title", None)
    if isinstance(title, str) and title:
        return title
    return stem


def _describe_simulator(cls: type) -> ListedSimulator:
    """Describe one simulator class."""
    stem = cls.__name__.removesuffix("Simulator")
    title = _catalog_title(cls, stem)
    document = inspect.getdoc(cls)
    detail = stem if document is None else document.split("\n", 1)[0].replace("``", "")
    parameters = [
        parameter
        for parameter in inspect.signature(cls).parameters.values()
        if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and parameter.name not in {"self", "cls"}
    ]
    observables = any(parameter.name == "observables" for parameter in parameters)
    return {
        "id": stem.lower(),
        "title": title,
        "detail": detail,
        "phrase": title,
        "setup": _simulator_setup(cls, parameters),
        "observables": observables,
        "samples": bool(getattr(cls, "requires_sampling_backend", False)),
        "closed_system": bool(getattr(cls, "closed_system", False)),
        "fields": _simulator_fields(parameters, observables),
    }


def _simulator_fields(parameters: list[inspect.Parameter], observables: bool) -> list[ListedSimulatorField]:
    """Return chip fields for the constructor parameters the page can edit."""
    listed: list[ListedSimulatorField] = []
    for parameter in parameters:
        spec = _CHIP_FIELDS.get(parameter.name)
        if spec is None:
            continue
        listed.append(_simulator_field(parameter, spec, observables))
    return listed


def _simulator_field(parameter: inspect.Parameter, spec: _ChipField, observables: bool) -> ListedSimulatorField:
    """Describe one chip parameter."""
    default = _field_default(parameter, spec, observables)
    if spec.kind == "choice":
        return {
            "name": parameter.name,
            "label": spec.label,
            "kind": "choice",
            "default": default,
            "choices": _literal_choices(parameter.annotation) or [],
        }
    listed: ListedSimulatorField = {
        "name": parameter.name,
        "label": spec.label,
        "kind": "integer",
        "default": default,
    }
    if spec.minimum is not None:
        listed["minimum"] = spec.minimum
    if spec.maximum is not None:
        listed["maximum"] = spec.maximum
    return listed


def _field_default(parameter: inspect.Parameter, spec: _ChipField, observables: bool) -> str:
    """Return the chip text for ``parameter``."""
    if observables and spec.observables_default is not None:
        return spec.observables_default
    if spec.use_constructor_default and isinstance(parameter.default, int) and not isinstance(parameter.default, bool):
        return str(parameter.default)
    return spec.default


def _literal_choices(annotation: object) -> list[str] | None:
    """Return string members of a ``Literal`` annotation."""
    if get_origin(annotation) is not Literal:
        return None
    choices: list[str] = []
    for item in get_args(annotation):
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            return None
        choices.append(str(item))
    return choices or None


def _simulator_setup(cls: type, parameters: list[inspect.Parameter]) -> str:
    """Return the preview call for ``cls``, with page values left as placeholders."""
    arguments: list[str] = []
    for parameter in parameters:
        name = parameter.name
        if name == "basis":
            if arguments:
                arguments[-1] = f"{arguments[-1]}{{basis}}"
            else:
                arguments.append("{basis}")
            continue
        structural = _STRUCTURAL.get(name)
        if structural is not None:
            arguments.append(structural)
            continue
        if name in _CHIP_FIELDS:
            arguments.append(f"{name}={{{name}}}")
            continue
        if parameter.default is inspect.Parameter.empty:
            arguments.append(name)
    if not arguments:
        return f"{{name}} = {cls.__name__}()"
    body = "".join(f"    {argument},\n" for argument in arguments)
    return f"{{name}} = {cls.__name__}(\n{body})"
