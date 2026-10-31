"""List the concrete simulators for the builder page."""

import importlib
import inspect
from typing import TypedDict

from shadowsim import simulators
from shadowsim._optional import import_optional
from shadowsim.simulators.simulator import Simulator


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
    trotter: bool


def listed_simulators() -> list[ListedSimulator]:
    """Return the exported simulator classes whose modules import successfully.

    :class:`~shadowsim.simulators.simulator.Simulator` itself is omitted. A class
    is skipped when its extra is not installed. QuTiP is the one that records
    explicit observables; the others take a circuit backend. ``samples`` is true
    when the class sets ``requires_sampling_backend``, so the page pairs it only
    with a backend that has a shot budget. ``closed_system`` is true when the
    class sets that attribute. ``trotter`` is true when the constructor takes
    ``trotter_depth``.
    ``setup`` names the class and leaves the page's constructor values as
    placeholders: ``{name}``, ``{hamiltonians}``, ``{lindblads}``, ``{qubits}``,
    ``{total}``, and ``{time_steps}``. A circuit simulator also leaves
    ``{num_steps}``, ``{seed}``, ``{basis}``, and ``{backend}``. One whose
    constructor takes ``trotter_depth`` also leaves ``{trotter_depth}`` and
    ``{order}``.

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


def _describe_simulator(cls: type) -> ListedSimulator:
    """Describe one simulator class."""
    title = cls.__name__.removesuffix("Simulator")
    document = inspect.getdoc(cls)
    detail = title if document is None else document.split("\n", 1)[0].replace("``", "")
    parameters = inspect.signature(cls).parameters
    observables = "observables" in parameters
    samples = bool(getattr(cls, "requires_sampling_backend", False))
    closed_system = bool(getattr(cls, "closed_system", False))
    trotter = "trotter_depth" in parameters
    if observables:
        setup = (
            f"{{name}} = {cls.__name__}({{hamiltonians}}, {{lindblads}}, state,\n"
            "                    e_ops, num_qubits={qubits},\n"
            "                    total_time={total}, time_steps={time_steps})"
        )
    else:
        product = "    trotter_depth={trotter_depth},\n    order={order},\n" if trotter else ""
        setup = (
            f"{{name}} = {cls.__name__}(\n"
            "    {hamiltonians},\n"
            "    {lindblads},\n"
            "    state,\n"
            "    num_qubits={qubits},\n"
            "    total_time={total},\n"
            "    time_steps={time_steps},\n"
            "    num_steps={num_steps},\n"
            f"{product}"
            "    seed={seed}{basis},\n"
            "    circuit_backend={backend},\n"
            ")"
        )
    return {
        "id": title.lower(),
        "title": title,
        "detail": detail,
        "phrase": title,
        "setup": setup,
        "observables": observables,
        "samples": samples,
        "closed_system": closed_system,
        "trotter": trotter,
    }
