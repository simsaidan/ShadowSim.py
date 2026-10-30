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


def listed_simulators() -> list[ListedSimulator]:
    """Return the exported simulator classes whose modules import successfully.

    :class:`~shadowsim.simulators.simulator.Simulator` itself is omitted. A class
    is skipped when its extra is not installed. QuTiP is the one that records
    explicit observables; the others take a circuit backend. ``samples`` is true
    when the class sets ``requires_sampling_backend``, so the page pairs it only
    with a backend that has a shot budget.

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
    observables = "observables" in inspect.signature(cls).parameters
    samples = bool(getattr(cls, "requires_sampling_backend", False))
    if observables:
        setup = (
            f"{{name}} = {cls.__name__}(model.full_hamiltonians, model.c_ops_full, state,\n"
            "                    e_ops, num_qubits=model.num_qubits,\n"
            "                    total_time={total}, time_steps=101)"
        )
    else:
        setup = (
            f"{{name}} = {cls.__name__}(\n"
            "    model.local_hamiltonians,\n"
            "    model.c_ops_local,\n"
            "    state,\n"
            "    num_qubits=model.num_qubits,\n"
            "    total_time={total},\n"
            "    time_steps=101,\n"
            "    num_steps=20,\n"
            "    circuit_backend=circuit_backend,\n"
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
    }
