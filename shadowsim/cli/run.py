"""Build a simulator from a builder-page selection."""

import importlib
import inspect
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

from shadowsim import models, simulators
from shadowsim._optional import import_optional
from shadowsim.backends import _EXPORTS as _BACKEND_EXPORTS
from shadowsim.backends.catalog import ListedBackend, listed_backends
from shadowsim.benchmarking.benchmark import Benchmark
from shadowsim.cli.catalog import (
    _PAGE_QUBIT_CAP,
    action_record,
    labels_for,
    listed_states,
    measurement_record,
    measurements_for,
    observables_for,
    prepare_state,
)
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.models.catalog import ListedParam, listed_models
from shadowsim.models.ising import IsingModel
from shadowsim.models.tavis_cummings import TavisCummingsModel
from shadowsim.simulators.catalog import ListedSimulatorField, _chip_default, _chip_maximum, _describe_simulator
from shadowsim.simulators.reducers import Measurement
from shadowsim.simulators.result import SimulationResult, _resource_record, save_resource_metrics
from shadowsim.simulators.simulator import Simulator
from shadowsim.utils.hermitian import hermitian

# A page click cannot afford the class defaults of 101 points and 10_000 shots.
# The chip defaults and bounds live on the simulator catalog.
_OBSERVABLES_TIME_STEPS = int(_chip_default("time_steps", observables=True))
_CIRCUIT_SHOTS = 256
_MAX_OPERATOR_QUBITS = 8
_MAX_TIME_STEPS = _chip_maximum("time_steps")
_MAX_NUM_STEPS = _chip_maximum("num_steps")
_MAX_TROTTER_DEPTH = _chip_maximum("trotter_depth")
_MAX_SHOTS = 100000


def _page_limits() -> dict[str, object]:
    """Return the builder page caps.

    State caps are each catalog entry's ``field.cap``. Basis and Gray
    preparation also reject a longer bit string. The amplitude count is the
    page typing cap and is not enforced on a posted list. A posted factory is
    capped by the qubit count it reports. Every other field is a cap a
    validator in this module enforces.
    """
    return {
        "states": {item["id"]: item["field"]["cap"] for item in listed_states()},
        "operatorQubits": _MAX_OPERATOR_QUBITS,
        "timeSteps": _MAX_TIME_STEPS,
        "numSteps": _MAX_NUM_STEPS,
        "trotterDepth": _MAX_TROTTER_DEPTH,
        "shots": _MAX_SHOTS,
    }


@dataclass(frozen=True)
class _AddedModel:
    """Operators posted from the Add cards."""

    num_qubits: int
    full_hamiltonians: list[Hamiltonian]
    local_hamiltonians: list[LocalHamiltonian]
    c_ops_full: list[Operator]
    c_ops_local: list[LocalOperator]


_FactoryModel = IsingModel | TavisCummingsModel
_PageModel = _FactoryModel | _AddedModel

_RUN_VERSION = 1
_DOCUMENT_KEYS = frozenset({"version", "total", "state", "model", "simulators", "measure", "actions"})
_MODEL_KEYS = frozenset({"id", "arguments", "terms", "qubits"})
_MEASURE_KEYS = frozenset({"id", "sites", "expression"})
_ACTION_KEYS = frozenset({"ids", "save_path", "export_path"})
_ENTRY_KEYS = frozenset({"id", "arguments", "backend"})
_BACKEND_KEYS = frozenset({"id", "arguments"})
_STATE_KEYS = frozenset({"id", "value"})


@dataclass(frozen=True)
class _SimulatorEntry:
    """One ``simulators`` entry after the document has been read."""

    id: str
    arguments: Mapping[str, object]
    backend_id: str
    backend_arguments: Mapping[str, object]


@dataclass(frozen=True)
class _RunDocument:
    """A version 1 run document."""

    total: object
    state_id: str
    state_value: object
    model: Mapping[str, object]
    simulators: tuple[_SimulatorEntry, ...]
    measure: Mapping[str, object]
    action_ids: frozenset[object]
    actions: Mapping[str, object]


@dataclass(frozen=True)
class _PreparedRun:
    """Simulators built from a run document, before any of them runs."""

    document: _RunDocument
    simulators: tuple[Simulator, ...]
    directory: Path | None
    export_to: Path | None
    benchmark: Benchmark | None


def _exact_keys(body: Mapping[str, object], allowed: frozenset[str]) -> None:
    """Reject a key the document section does not list."""
    extra = set(body) - allowed
    if extra:
        raise ValueError(f"unknown field {min(extra)}")


def _object(body: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return the object stored at ``key``."""
    value = body.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _text(value: object) -> str:
    """Return ``value`` when it is a string, otherwise an empty string."""
    if isinstance(value, str):
        return value
    return ""


def _simulator_entry(entry: object) -> _SimulatorEntry:
    """Return one simulator entry.

    Raises:
        ValueError: ``entry`` is not an object, or a nested value has the wrong shape.
    """
    if not isinstance(entry, Mapping):
        raise ValueError("each simulator must be an object")
    _exact_keys(entry, _ENTRY_KEYS)
    arguments = entry.get("arguments")
    if not isinstance(arguments, Mapping):
        raise ValueError("simulator arguments must be an object")
    backend = entry.get("backend")
    if backend is None:
        return _SimulatorEntry(_text(entry.get("id")), arguments, "", {})
    if not isinstance(backend, Mapping):
        raise ValueError("backend must be an object")
    _exact_keys(backend, _BACKEND_KEYS)
    backend_arguments = backend.get("arguments")
    if not isinstance(backend_arguments, Mapping):
        raise ValueError("backend arguments must be an object")
    return _SimulatorEntry(_text(entry.get("id")), arguments, _text(backend.get("id")), backend_arguments)


def _read_document(body: Mapping[str, object]) -> _RunDocument:
    """Return ``body`` as a version 1 run document.

    Raises:
        ValueError: ``version`` is missing or unknown, a section has the wrong
            shape, or ``body`` carries a key this version does not list.
    """
    _exact_keys(body, _DOCUMENT_KEYS)
    if "version" not in body:
        raise ValueError("version must be 1")
    version = body["version"]
    if type(version) is not int or version != _RUN_VERSION:
        raise ValueError(f"unknown version {version}")
    state = _object(body, "state")
    _exact_keys(state, _STATE_KEYS)
    model = _object(body, "model")
    _exact_keys(model, _MODEL_KEYS)
    measure = _object(body, "measure")
    _exact_keys(measure, _MEASURE_KEYS)
    actions = _object(body, "actions")
    _exact_keys(actions, _ACTION_KEYS)
    raw_ids = actions.get("ids")
    if not isinstance(raw_ids, list):
        raise ValueError("actions must list ids")
    raw_simulators = body.get("simulators")
    if not isinstance(raw_simulators, list) or len(raw_simulators) == 0:
        raise ValueError("simulators must be a non-empty list")
    return _RunDocument(
        total=body.get("total"),
        state_id=_text(state.get("id")),
        state_value=state.get("value"),
        model=model,
        simulators=tuple(_simulator_entry(entry) for entry in raw_simulators),
        measure=measure,
        action_ids=frozenset(raw_ids),
        actions=actions,
    )


def _page_model(model: Mapping[str, object]) -> _PageModel:
    """Build the posted model.

    A non-empty ``terms`` list is the model. Otherwise ``id`` names a factory
    and ``arguments`` is bound from that factory's signature.
    """
    terms = model.get("terms")
    if isinstance(terms, list) and terms:
        return _added_model(terms, model.get("qubits"))
    arguments = model.get("arguments")
    if not isinstance(arguments, Mapping):
        raise ValueError("factory arguments must be an object")
    return _model(_text(model.get("id")), arguments)


def build_simulator(selection: Mapping[str, object], *, simulator: int = 0) -> Simulator:
    """Build one simulator from a version 1 run document.

    ``selection`` is the document :func:`run_page` reads. ``version`` must be 1.
    A missing version fails with ``version must be 1``. Any other version fails
    with that value in the message. ``simulator`` selects an entry of
    ``simulators``; the default is the first.

    Args:
        selection: ``total`` is the shared evolution time. ``state`` has ``id``
            and ``value``. ``model`` is ``id`` plus ``arguments``, or ``terms``
            plus ``qubits``. Each simulator has ``id``, ``arguments``, and
            ``backend`` (null, or ``id`` plus ``arguments``). ``state.id`` is an
            id from :func:`shadowsim.cli.catalog.listed_states`. ``measure`` has
            ``id``. ``model`` records the factory's ``e_ops`` on an observables
            simulator and applies its ``measurements`` on a circuit simulator.
            The chart names are those measurement labels. An added Hamiltonian
            also has ``sites``, plus ``expression`` for ``counts``. Its
            ``measure.id`` is an id from
            :func:`shadowsim.cli.catalog.listed_measurements`. A factory model
            rejects a catalog id, and an added Hamiltonian rejects ``model``.
            ``actions`` is ignored. The simulator ``id`` is
            an id from :func:`shadowsim.simulators.catalog.listed_simulators`.
            A simulator that records observables ignores a missing backend. A
            circuit simulator's ``backend`` is an id from
            :func:`shadowsim.backends.catalog.listed_backends`, and one that
            samples needs a backend with a shot budget. An added Hamiltonian's
            ``measure`` of ``x``, ``y``, or ``z`` records that Pauli's expectation
            on each selected qubit for every simulator. ``counts`` evaluates
            ``expression`` (see :class:`~shadowsim.simulators.Measurement`) on the
            shot counts of the selected qubits, in ``sites`` order. It needs a
            backend with a shot budget, so an observables simulator and a backend
            without one reject it. A circuit simulator records counts only;
            :func:`run_page` reads them.
            ``model`` is a factory name from :func:`shadowsim.models.catalog.listed_models`.
            A non-empty ``terms`` list is the model instead: each item has ``id``
            and ``matrix``, and local terms also have ``sites``. At least one
            Hamiltonian term is required.
            Factory ``arguments`` use the factory's parameter names. A posted
            name the factory does not take fails. ``n_qubits`` is at most 15.
            An integer field is an integer of at least the catalog minimum, and
            a missing field keeps the factory default. A factory that does not
            take ``n_qubits`` must report a qubit count, and that count is at
            most 15. The other arguments are finite reals or numeric text. A
            per-emitter value is a scalar or a sequence whose length is
            ``n_emitters``, or length 1 when the factory has no emitter count.
            ``edges`` is empty, dash pairs such as ``0-1, 1-2``, or a list of
            pairs.
            ``state.value`` is the payload for ``state.id``. A basis or Gray code
            is a string of 0 and 1 whose length is the qubit count, at most 15
            characters. Angle is one finite real number per qubit. Amplitude is
            a non-zero list of finite real numbers, and the padded vector must
            use the model's qubit count. For an added Hamiltonian,
            ``measure.sites`` lists qubit indexes to measure. Missing ``sites``
            measures every qubit. A factory measurement already names its qubits.
            Simulator ``arguments`` are the catalog fields for that constructor.
            ``time_steps`` is from 1 to 500. Missing it uses 101 when the
            constructor records observables and 11 otherwise. ``num_steps`` is
            from 1 to 100 and defaults to 4 when the constructor takes it.
            ``trotter_depth`` is from 1 to 100 and ``order`` is 1 or 2; both
            default to the constructor value. ``seed`` is an integer and
            defaults to 0. A missing field uses that default. A posted name the
            constructor does not take is ignored. A backend with a shot budget
            reads ``shots`` (1 to 100000) from the backend arguments. A posted
            ``time_steps`` value is checked before the simulator extra is
            imported. A posted ``shots`` value is checked then too when that
            backend has a shot budget, and also when no backend module can be
            imported. A gate-list field, such as Aer's ``basis_gates``, is a
            comma-separated string or a sequence of names. A blank value keeps
            that backend's own basis. Any other backend field is a non-negative
            number, and a missing value keeps the catalog default. A simulator
            with ``closed_system`` set rejects Lindblad operators. A missing
            shot count uses the page budget.
        simulator: Index of the ``simulators`` entry to build. Defaults to the first.

    Returns:
        A simulator that has not been run.

    Raises:
        ValueError: The document cannot run in this slice.
        ImportError: The extra required by the simulator or backend is not installed.
    """
    document = _read_document(selection)
    return _build_simulator(document, simulator)


def _build_simulator(document: _RunDocument, index: int) -> Simulator:
    """Build ``document.simulators[index]``. The document has already been read."""
    entry = document.simulators[index]
    class_name, module_name, extra = _simulator_export(entry.id)
    backend = entry.backend_id
    if backend and backend not in _backend_ids():
        raise ValueError("unknown backend")
    if not any(item["id"] == document.state_id for item in listed_states()):
        raise ValueError("unknown initial state")
    total_time = _positive_number(document.total)
    model = _page_model(document.model)
    state = _initial_state(document.state_id, model.num_qubits, document.state_value)
    measure_id = _text(document.measure.get("id"))
    _require_measure(model, measure_id)
    if measure_id == "model":
        sites: list[int] = []
    else:
        sites = _measure_sites(document.measure, model.num_qubits)
        _measurements(document.measure, model.num_qubits)
    if class_name == "QutipSimulator":
        _reject_counts(measure_id, "QuTiP")
        steps = _selection_positive_int(
            entry.arguments, "time_steps", _OBSERVABLES_TIME_STEPS, "time steps", maximum=_MAX_TIME_STEPS
        )
        return _qutip_simulator(model, state, measure_id, total_time, steps, sites)
    if "time_steps" in entry.arguments:
        _selection_positive_int(
            entry.arguments, "time_steps", _OBSERVABLES_TIME_STEPS, "time steps", maximum=_MAX_TIME_STEPS
        )
    if backend and "shots" in entry.backend_arguments and _backend_has_shot_budget(backend):
        _selection_positive_int(entry.backend_arguments, "shots", _CIRCUIT_SHOTS, "shots", maximum=_MAX_SHOTS)
    cls = _load_exported(module_name, extra, class_name, "unknown simulator")
    if "observables" in inspect.signature(cls).parameters:
        _reject_counts(measure_id, class_name.removesuffix("Simulator"))
        posted = _simulator_arguments(cls, entry.arguments)
        if "time_steps" in posted:
            steps = posted["time_steps"]
        else:
            steps = _selection_positive_int(
                entry.arguments, "time_steps", _OBSERVABLES_TIME_STEPS, "time steps", maximum=_MAX_TIME_STEPS
            )
        return _qutip_simulator(model, state, measure_id, total_time, steps, sites, cls)
    if not backend:
        raise ValueError("unknown backend")
    record = _backend_record(backend)
    if not record["shots"]:
        _reject_counts(measure_id, record["title"])
    if getattr(cls, "requires_sampling_backend", False) and not record["shots"]:
        raise ValueError(f"{class_name.removesuffix('Simulator')} needs a backend with a shot budget")
    return _circuit_simulator(
        cls,
        entry.arguments,
        entry.backend_arguments,
        model,
        state,
        measure_id,
        total_time,
        sites,
        record,
    )


def _prepare_page(selection: Mapping[str, object], *, output_root: Path | None) -> _PreparedRun:
    """Read ``selection`` and build every simulator. Do not simulate.

    Save and export paths are checked before the build. Two or more entries
    construct a :class:`~shadowsim.benchmarking.benchmark.Benchmark` so a
    mismatched time grid fails here. The benchmark is not run, and nothing is written.

    Raises:
        ValueError: The document cannot be built, an action id is not listed, or
            a save or export path is illegal.
        ImportError: The extra required by a simulator or backend is not installed.
    """
    document = _read_document(selection)
    _require_actions(document.action_ids)
    directory = _save_directory(document, output_root)
    export_to = _export_location(document, output_root)
    simulators = tuple(_build_simulator(document, index) for index in range(len(document.simulators)))
    benchmark = Benchmark(simulators[0], *simulators[1:]) if len(simulators) >= 2 else None
    return _PreparedRun(
        document=document,
        simulators=simulators,
        directory=directory,
        export_to=export_to,
        benchmark=benchmark,
    )


def check_page(selection: Mapping[str, object], *, output_root: Path | None = None) -> dict[str, object]:
    """Build a version 1 document and return its qubit count. Do not simulate.

    This is the build :func:`run_page` performs before it evolves the system.
    One entry builds that simulator. Two or more build every entry and reject a
    mismatched time grid. Nothing is written. ``qubits`` is the first simulator's
    ``num_qubits``.

    Args:
        selection: The version 1 document described on :func:`build_simulator`.
        output_root: Directory that save and export paths must stay under.
            ``None`` leaves those paths unchanged.

    Returns:
        ``qubits``, the qubit count of the built model. A factory model also
        returns ``measurements``, one ``label`` and ``qubits`` entry for each
        measurement the factory defines.

    Raises:
        ValueError: The document cannot run, including an integer field below
            its minimum, an edge list, or a qubit count above 15, an action id
            that is not listed, or a save or export path outside ``output_root``.
        ImportError: The extra required by a simulator or backend is not installed.
    """
    prepared = _prepare_page(selection, output_root=output_root)
    payload: dict[str, object] = {"qubits": prepared.simulators[0].num_qubits}
    if _text(prepared.document.measure.get("id")) == "model":
        model = cast(_FactoryModel, _page_model(prepared.document.model))
        payload["measurements"] = [
            {"label": item.label, "qubits": list(item.qubits)} for item in _model_records(model)[1]
        ]
    return payload


def run_page(selection: Mapping[str, object], *, output_root: Path | None = None) -> dict[str, object]:
    """Run every simulator in a version 1 document.

    The simulators are built by the same steps as :func:`check_page`. None of
    them runs until that build succeeds. One ``simulators`` entry is one simulation.
    Two or more is a benchmark. The first entry is the reference. Any exported
    simulator may be the reference or a challenger. Every entry must share ``total``
    and ``time_steps``, because :class:`~shadowsim.benchmarking.benchmark.Benchmark`
    compares one time grid. ``time_steps`` is read from that entry's arguments.
    ``actions`` lists the ids to run. An id that is not in
    :func:`shadowsim.cli.catalog.listed_actions` is an error. ``save`` writes each
    result under ``save_path``, or that action's catalog default when the key is
    missing. One result is the directory itself.
    A benchmark writes ``sim_1``, ``sim_2``, and so on inside it. ``export`` writes
    metrics JSON under ``export_path``, or that action's catalog default when
    the key is missing.
    A benchmark uses :meth:`~shadowsim.benchmarking.benchmark.Benchmark.save_error_metrics`.
    One simulator writes its runtime, shot budget, and circuit metrics with
    :func:`~shadowsim.simulators.result.save_resource_metrics`. ``plot`` is drawn by the
    page. The payload names each observable in ``labels`` and lists wall time,
    shot budget, and circuit metrics in ``resources``. Circuit metrics are
    ``"N/A"`` when the backend cannot measure the final-time circuit. A benchmark
    fills ``resources`` from
    :meth:`~shadowsim.benchmarking.benchmark.Benchmark.resource_metrics`, and each
    series names its curves ``{simulator} · {label}``. Save and export both run
    when both are selected. When ``output_root`` is set, ``save_path`` and
    ``export_path`` must resolve under that directory.
    A relative path is resolved from the working directory.

    Args:
        selection: The version 1 document described on :func:`build_simulator`.
        output_root: Directory that save and export paths must stay under.
            ``None`` leaves those paths unchanged.
    """
    prepared = _prepare_page(selection, output_root=output_root)
    if prepared.benchmark is not None:
        return _run_benchmark(selection, prepared, prepared.benchmark)
    simulator = prepared.simulators[0]
    simulator.simulate()
    result = _measured_result(simulator, selection)
    payload = _result_payload(result, simulator, _page_model(prepared.document.model), prepared.document.measure)
    saved = _write_results(prepared.directory, [result])
    if saved:
        payload["saved"] = saved
    exported = _export_resources(prepared.export_to, simulator, result.runtime)
    if exported:
        payload["exported"] = exported
    return payload


def _measured_result(simulator: Simulator, selection: Mapping[str, object]) -> SimulationResult:
    """Read the page measurements from a simulated circuit simulator and return its result.

    An observables simulator already recorded its curves, so its result is returned
    unchanged. A factory model's curves are its ``e_ops``. An added Hamiltonian's
    curves are the selected Pauli operators.

    Raises:
        ValueError: ``simulator`` has not been simulated, or the measurement
            cannot be read from its result.
    """
    document = _read_document(selection)
    if getattr(simulator, "circuit_backend", None) is None:
        if simulator.last_result is None:
            raise ValueError("Results are not available. Please run the simulation first.")
        return simulator.last_result
    return simulator.measure(_page_measurements(_page_model(document.model), document.measure))


def _result_payload(
    result: SimulationResult,
    simulator: Simulator,
    model: _PageModel,
    measure: Mapping[str, object],
) -> dict[str, object]:
    """Return the curves, names, and resource record the page chart draws."""
    return {
        "times": result.times.tolist(),
        "observables": [curve.tolist() for curve in result.observables],
        "labels": _chart_labels(model, measure),
        "resources": [_resource_record(simulator, result.runtime)],
        "runtime": result.runtime,
        "algorithm": result.algorithm,
    }


def _path_under_root(path: Path, root: Path, label: str) -> Path:
    """Return ``path`` resolved from the working directory when it stays inside ``root``.

    Raises:
        ValueError: The resolved path is outside ``root``.
    """
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} must stay under {resolved_root}")
    return resolved


def _require_actions(action_ids: frozenset[object]) -> None:
    """Reject an action id that the catalog does not list.

    Raises:
        ValueError: An id is not listed.
    """
    for action_id in action_ids:
        action_record(cast(str, action_id))


def _action_path_default(action_id: str) -> str:
    """Return the catalog default path for a path action."""
    return action_record(action_id)["field"]["default"]


def _save_directory(document: _RunDocument, output_root: Path | None) -> Path | None:
    """Return the save directory, or ``None`` when this run is not saved.

    Raises:
        ValueError: ``save`` is selected and ``save_path`` is not a path, or it
            resolves outside ``output_root``.
    """
    if "save" not in document.action_ids:
        return None
    default = _action_path_default("save")
    raw = document.actions.get("save_path", default)
    if raw is None:
        raw = default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("save path must be a path")
    path = Path(raw.strip())
    if output_root is None:
        return path
    return _path_under_root(path, output_root, "save path")


def _export_location(document: _RunDocument, output_root: Path | None) -> Path | None:
    """Return where to write metrics JSON, or ``None`` when this run is not exported.

    Raises:
        ValueError: ``export`` is selected and ``export_path`` is not a path, or
            it resolves outside ``output_root``.
    """
    if "export" not in document.action_ids:
        return None
    default = _action_path_default("export")
    raw = document.actions.get("export_path", default)
    if raw is None:
        raw = default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("export path must be a path")
    path = Path(raw.strip())
    if output_root is None:
        return path
    return _path_under_root(path, output_root, "export path")


def _export_resources(location: Path | None, simulator: Simulator, wall_time: float | None) -> str | None:
    """Write one simulator's runtime and shot budget. A ``.json`` path is that file."""
    if location is None:
        return None
    if location.suffix == ".json":
        written = save_resource_metrics(simulator, wall_time, path=location)
    else:
        written = save_resource_metrics(simulator, wall_time, output_dir=location)
    return str(written)


def _export_benchmark(location: Path | None, benchmark: Benchmark) -> str | None:
    """Write benchmark error and resource metrics. A ``.json`` path is that file."""
    if location is None:
        return None
    if location.suffix == ".json":
        return str(benchmark.save_error_metrics(path=location))
    return str(benchmark.save_error_metrics(output_dir=location))


def _write_results(directory: Path | None, results: list[SimulationResult]) -> list[str]:
    """Write results under ``directory``. Several results each get a ``sim_N`` folder."""
    if directory is None:
        return []
    if len(results) == 1:
        return [str(results[0].save(directory))]
    return [str(result.save(directory / f"sim_{index + 1}")) for index, result in enumerate(results)]


def _run_benchmark(
    selection: Mapping[str, object],
    prepared: _PreparedRun,
    benchmark: Benchmark,
) -> dict[str, object]:
    """Run the prepared benchmark and return curves, names, and resources.

    Each series name is that simulator's resource ``title``, so the legend
    labels use the same display string.
    """
    simulators = prepared.simulators
    benchmark.run()
    recorded = [_measured_result(simulator, selection) for simulator in simulators]
    resources = benchmark.resource_metrics()
    labels = _chart_labels(_page_model(prepared.document.model), prepared.document.measure)
    series: list[dict[str, object]] = []
    for result, resource in zip(recorded, resources, strict=True):
        name = str(resource["title"])
        series.append(
            {
                "name": name,
                "labels": [f"{name} · {label}" for label in labels],
                "observables": [curve.tolist() for curve in result.observables],
            }
        )
    reference = simulators[0].last_result
    assert reference is not None
    wall_times = [item["wall_time_s"] for item in resources]
    payload: dict[str, object] = {
        "times": reference.times.tolist(),
        "observables": [curve.tolist() for curve in reference.observables],
        "labels": labels,
        "series": series,
        "errors": benchmark.error_metrics(),
        "resources": resources,
        "runtime": float(sum(wall_times)),
        "algorithm": "benchmark",
    }
    saved = _write_results(
        prepared.directory,
        [item.last_result for item in simulators if item.last_result is not None],
    )
    if saved:
        payload["saved"] = saved
    exported = _export_benchmark(prepared.export_to, benchmark)
    if exported:
        payload["exported"] = exported
    return payload


def _qutip_simulator(
    model: _PageModel,
    state: State,
    measure_id: str,
    total_time: float,
    time_steps: int,
    sites: list[int],
    cls: Any = None,
) -> Simulator:
    """Build an observables simulator for the posted measurement.

    ``model`` records the factory ``e_ops``. An added Hamiltonian records one
    Pauli on each selected qubit. QuTiP is imported when ``cls`` is omitted, so
    a test can replace this function without importing that extra.
    """
    if measure_id == "model":
        observables = _model_records(cast(_FactoryModel, model))[0]
    else:
        observables = _observables(model.num_qubits, measure_id, sites)
    if cls is None:
        qutip_simulator = import_optional("shadowsim.simulators.qutip_simulator", extra="qutip")
        cls = qutip_simulator.QutipSimulator
    return cls(
        model.full_hamiltonians,
        model.c_ops_full,
        state,
        observables,
        num_qubits=model.num_qubits,
        total_time=total_time,
        time_steps=time_steps,
    )


def _circuit_simulator(
    cls: Any,
    arguments: Mapping[str, object],
    backend_arguments: Mapping[str, object],
    model: _PageModel,
    state: State,
    measure_id: str,
    total_time: float,
    sites: list[int],
    record: ListedBackend,
) -> Simulator:
    """Build a circuit simulator on the catalog backend ``record`` names.

    A factory model is measured in Z. Its expressions already name the
    computational-basis counts they read. An added Hamiltonian whose catalog
    record sets ``rotate`` reads those qubits in that record's letter and every
    other qubit in Z. The others measure every qubit in Z. Chip values come
    from the catalog fields on ``cls``. A posted
    name that is not one of those fields is ignored. The simulator records
    counts, or Pauli expectations when the backend has no shot budget, which
    :func:`_measured_result` reads.
    """
    posted = _simulator_arguments(cls, arguments)
    if getattr(cls, "closed_system", False) and model.c_ops_local:
        raise ValueError(f"{cls.__name__.removesuffix('Simulator')} is closed-system only")
    circuit_backend = _make_backend(record, backend_arguments)
    if measure_id != "model":
        measured = measurement_record(measure_id)
        if measured.get("rotate"):
            posted["basis"] = _pauli_basis(model.num_qubits, sites, str(measured.get("letter", "")))
    return cls(
        model.local_hamiltonians,
        model.c_ops_local,
        state,
        num_qubits=model.num_qubits,
        total_time=total_time,
        circuit_backend=circuit_backend,
        **posted,
    )


def _simulator_arguments(cls: type, arguments: Mapping[str, object]) -> dict[str, Any]:
    """Return the catalog chip values for ``cls``.

    A missing key uses that field's default. A posted name that is not a chip
    on this constructor is ignored.
    """
    values: dict[str, Any] = {}
    for field in _describe_simulator(cls)["fields"]:
        values[field["name"]] = _posted_field(arguments, field)
    return values


def _posted_field(arguments: Mapping[str, object], field: ListedSimulatorField) -> int:
    """Return one posted chip value, or the field default when it was omitted."""
    name = field["name"]
    phrase = _field_phrase(field["label"])
    default = int(field["default"])
    if field["kind"] == "choice":
        return _posted_choice(arguments, name, default, phrase, list(field.get("choices") or []))
    maximum = field.get("maximum")
    if isinstance(maximum, int):
        return _selection_positive_int(arguments, name, default, phrase, maximum=maximum)
    return _selection_integer(arguments, name, default, phrase)


def _posted_choice(
    arguments: Mapping[str, object],
    name: str,
    default: int,
    phrase: str,
    choices: list[str],
) -> int:
    """Return a posted choice, or ``default`` when ``name`` was omitted.

    Raises:
        ValueError: The posted value is not an integer, or it is not one of
            ``choices``.
    """
    if name not in arguments:
        return default
    number = _named_integer(arguments[name], phrase)
    allowed = [int(choice) for choice in choices]
    if number not in allowed:
        raise ValueError(f"{phrase} must be {' or '.join(choices)}")
    return number


def _field_phrase(label: str) -> str:
    """Return the error phrase for a chip label.

    A leading capital is lowercased, so ``Time steps`` stays the existing
    ``time steps`` message. ``Trotter depth`` is already that phrase.
    """
    if label.startswith("Trotter"):
        return label
    return label[:1].lower() + label[1:]


def _reject_counts(measure_id: str, label: str) -> None:
    """Reject a counts measurement for a simulator or backend that returns expectations.

    A factory model's measurements are applied to shot counts by a circuit
    simulator. An observables simulator records ``e_ops`` instead, so this
    check does not apply to ``model``.

    Raises:
        ValueError: ``measure_id`` is not listed, or it is a counts measurement.
    """
    if measure_id == "model" or measurement_record(measure_id)["kind"] != "counts":
        return
    raise ValueError(f"{label} returns Pauli expectations, not shot counts; use Aer for a counts measurement")


def _simulator_export(simulator_id: str) -> tuple[str, str, str | None]:
    """Return the export entry whose catalog id is ``simulator_id``."""
    for class_name, (module_name, extra) in simulators._EXPORTS.items():
        if class_name.removesuffix("Simulator").lower() == simulator_id:
            return class_name, module_name, extra
    raise ValueError("unknown simulator")


def _backend_ids() -> set[str]:
    """Return catalog ids for exported backend classes, without importing them."""
    ids: set[str] = set()
    for class_name in _BACKEND_EXPORTS:
        if not class_name.endswith("Backend") or class_name == "CircuitBackend":
            continue
        title = class_name.removesuffix("CircuitBackend").removesuffix("Backend")
        ids.add(title.lower())
    return ids


def _load_exported(module_name: str, extra: str | None, class_name: str, missing: str) -> Any:
    """Import ``class_name`` from ``module_name``."""
    if extra is None:
        module = importlib.import_module(module_name)
    else:
        module = import_optional(module_name, extra=extra)
    value = getattr(module, class_name, None)
    if not isinstance(value, type):
        raise ValueError(missing)
    return value


def _backend_has_shot_budget(backend_id: str) -> bool:
    """Return whether ``backend_id`` reads a shot budget.

    A posted shot count is still checked when that backend's module cannot be
    imported, including when other backends imported and the catalog is only
    partial. The number is reported before the missing extra. A module that
    imports but is absent from the catalog does not read a shot budget.
    """
    try:
        records = listed_backends()
    except ImportError:
        return True
    for record in records:
        if record["id"] == backend_id:
            return bool(record["shots"])
    return _backend_import_failed(backend_id)


def _backend_import_failed(backend_id: str) -> bool:
    """Return whether the export named ``backend_id`` cannot be imported."""
    for class_name, (module_name, extra) in _BACKEND_EXPORTS.items():
        if not class_name.endswith("Backend") or class_name == "CircuitBackend":
            continue
        title = class_name.removesuffix("CircuitBackend").removesuffix("Backend")
        if title.lower() != backend_id:
            continue
        try:
            if extra is None:
                importlib.import_module(module_name)
            else:
                import_optional(module_name, extra=extra)
        except ImportError:
            return True
        return False
    return False


def _backend_record(backend_id: str) -> ListedBackend:
    """Return the catalog record for ``backend_id``.

    A known export whose module cannot be imported raises that import error.
    """
    for record in listed_backends():
        if record["id"] == backend_id:
            return record
    for class_name, (module_name, extra) in _BACKEND_EXPORTS.items():
        if not class_name.endswith("Backend") or class_name == "CircuitBackend":
            continue
        title = class_name.removesuffix("CircuitBackend").removesuffix("Backend")
        if title.lower() == backend_id:
            if extra is None:
                importlib.import_module(module_name)
            else:
                import_optional(module_name, extra=extra)
            break
    raise ValueError("unknown backend")


def _catalog_number(default: str, *, allow_inf: bool) -> float:
    """Return the numeric default published on a backend field."""
    text = default.strip().lower()
    if allow_inf and text in {"inf", "infinity"}:
        return math.inf
    return float(text)


def _make_backend(record: ListedBackend, selection: Mapping[str, object]) -> Any:
    """Construct the backend class named by ``record`` from the posted fields."""
    cls = _backend_class(record["setup"])
    kwargs: dict[str, object] = {}
    if record["shots"]:
        kwargs["shots"] = _selection_positive_int(selection, "shots", _CIRCUIT_SHOTS, "shots", maximum=_MAX_SHOTS)
    for field in record["fields"]:
        if field.get("kind") == "gates":
            kwargs[field["name"]] = _selection_basis_gates(selection, field["name"])
        else:
            kwargs[field["name"]] = _selection_nonnegative(
                selection,
                field["name"],
                _catalog_number(field["default"], allow_inf=field["allow_inf"]),
                field["label"].lower(),
                allow_inf=field["allow_inf"],
            )
    return cls(**kwargs)


def _backend_class(setup: str) -> Any:
    """Import the backend class named in a catalog ``setup`` string."""
    match = re.search(r"circuit_backend = ([A-Za-z0-9_]+)", setup)
    if match is None:
        raise ValueError("unknown backend")
    class_name = match.group(1)
    try:
        module_name, extra = _BACKEND_EXPORTS[class_name]
    except KeyError:
        raise ValueError("unknown backend") from None
    return _load_exported(module_name, extra, class_name, "unknown backend")


def _pauli_basis(num_qubits: int, sites: list[int], letter: str) -> str:
    """Return a basis that reads ``letter`` on ``sites`` and Z on every other qubit."""
    return "".join(letter if qubit in sites else "Z" for qubit in range(num_qubits))


def _selection_basis_gates(selection: Mapping[str, object], key: str = "basis_gates") -> list[str] | None:
    """Return gate names for ``key``, or ``None`` when the page left the field blank.

    A string is split on commas and whitespace. A sequence of strings is used
    as given. The backend checks that each name is a gate it can compile into.

    Raises:
        ValueError: ``key`` is not text or a sequence of gate names.
    """
    if key not in selection or selection[key] is None:
        return None
    value = selection[key]
    if isinstance(value, str):
        names = [part for part in re.split(r"[\s,]+", value.strip()) if part]
        if not value.strip():
            return None
        return names
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        names = list(value)
        if all(isinstance(name, str) for name in names):
            return names
    raise ValueError(f"{key} must be a sequence of gate names")


def _selection_nonnegative(
    selection: Mapping[str, object],
    key: str,
    default: float,
    name: str,
    *,
    allow_inf: bool,
) -> float:
    """Return a non-negative number from ``selection``, or ``default`` when the key is absent."""
    if key not in selection:
        return default
    value = selection[key]
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "":
            raise ValueError(f"{name} must be a non-negative number")
        if allow_inf and text in {"inf", "infinity"}:
            return math.inf
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be a non-negative number") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a non-negative number")
    number = float(value)
    if math.isnan(number) or number < 0 or (math.isinf(number) and not allow_inf):
        raise ValueError(f"{name} must be a non-negative number")
    return number


def _selection_positive_int(selection: Mapping[str, object], key: str, default: int, name: str, *, maximum: int) -> int:
    """Return a positive integer from ``selection``, or ``default`` when the key is absent.

    Args:
        selection: Posted builder fields.
        key: Field to read.
        default: Value when ``key`` is absent. Callers pass a page budget.
        name: Label used in the error.
        maximum: Inclusive upper bound for a posted value.

    Raises:
        ValueError: The posted value is not a positive integer, or is larger
            than ``maximum``.
    """
    if key not in selection:
        return default
    number = _named_integer(selection[key], name)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    if number > maximum:
        raise ValueError(f"{name} must be from 1 to {maximum}")
    return number


def _selection_integer(selection: Mapping[str, object], key: str, default: int, name: str) -> int:
    """Return an integer from ``selection``, or ``default`` when the key is absent."""
    if key not in selection:
        return default
    return _named_integer(selection[key], name)


def _named_integer(value: object, name: str) -> int:
    """Return ``value`` as an integer, rejecting booleans and fractional numbers."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{name} must be an integer")
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"{name} must be an integer") from None
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError(f"{name} must be an integer")
        return int(number)
    raise ValueError(f"{name} must be an integer")


def _positive_number(value: object) -> float:
    """Return ``value`` as a finite number greater than zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("total time must be a positive number")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("total time must be a positive number")
        try:
            number = float(text)
        except ValueError:
            raise ValueError("total time must be a positive number") from None
    else:
        number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("total time must be a positive number")
    return number


def _integer(value: object) -> int:
    """Return ``value`` as an integer, rejecting fractional numbers."""
    if isinstance(value, bool):
        raise ValueError("qubits must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("qubits must be an integer")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("qubits must be an integer")
        try:
            number = float(text)
        except ValueError:
            raise ValueError("qubits must be an integer") from None
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError("qubits must be an integer")
        return int(number)
    raise ValueError("qubits must be an integer")


def _added_model(terms: list[object], qubits: object) -> _AddedModel:
    """Build operators from posted Add cards. Validation happens before optional imports."""
    num_qubits = _integer(qubits)
    if num_qubits < 1 or num_qubits > _MAX_OPERATOR_QUBITS:
        raise ValueError(f"qubits must be from 1 to {_MAX_OPERATOR_QUBITS}")
    full: list[Hamiltonian] = []
    local: list[LocalHamiltonian] = []
    c_ops_full: list[Operator] = []
    c_ops_local: list[LocalOperator] = []
    saw_hamiltonian = False
    for item in terms:
        if not isinstance(item, Mapping):
            raise ValueError("terms must be operator objects")
        record = cast(Mapping[str, object], item)
        kind = record.get("id")
        matrix = _operator_matrix(record.get("matrix"))
        if kind == "hamiltonian":
            full_dim = 2**num_qubits
            if matrix.shape[0] != full_dim:
                raise ValueError(f"Hamiltonian matrix must be {full_dim}×{full_dim}")
            if not hermitian(matrix):
                raise ValueError("Hamiltonian matrix must be Hermitian")
            term = Hamiltonian(matrix)
            full.append(term)
            local.append(term.to_local_hamiltonian())
            saw_hamiltonian = True
        elif kind == "local_hamiltonian":
            sites = _acted_sites(record.get("sites"), num_qubits, matrix.shape[0])
            if not hermitian(matrix):
                raise ValueError("local Hamiltonian matrix must be Hermitian")
            term = LocalHamiltonian(matrix, sites)
            full.append(term)
            local.append(term)
            saw_hamiltonian = True
        elif kind == "lindblad":
            sites = _acted_sites(record.get("sites"), num_qubits, matrix.shape[0])
            operator = LocalOperator(matrix, sites)
            c_ops_local.append(operator)
            c_ops_full.append(operator.to_full_operator(num_qubits))
        else:
            raise ValueError("unknown operator")
    if not saw_hamiltonian:
        raise ValueError("add a Hamiltonian")
    return _AddedModel(num_qubits, full, local, c_ops_full, c_ops_local)


def _operator_matrix(value: object) -> np.ndarray:
    """Return a square complex matrix whose width is a power of two up to ``2**_MAX_OPERATOR_QUBITS``."""
    if not isinstance(value, list) or not value or any(not isinstance(row, list) for row in value):
        raise ValueError("matrix must be a square 2D array")
    rows = [[_complex_entry(entry) for entry in row] for row in value]
    size = len(rows)
    if any(len(row) != size for row in rows):
        raise ValueError("matrix must be a square 2D array")
    maximum = 2**_MAX_OPERATOR_QUBITS
    if size < 2 or size > maximum or size & (size - 1) != 0:
        raise ValueError(f"matrix size must be a power of two from 2 to {maximum}")
    return np.array(rows, dtype=np.complex128)


def _complex_entry(value: object) -> complex:
    """Return one matrix entry from a number or a ``[real, imag]`` pair."""
    if isinstance(value, list) and len(value) == 2:
        return complex(_finite_real(value[0]), _finite_real(value[1]))
    return complex(_finite_real(value))


def _finite_real(value: object) -> float:
    """Return a finite real number, rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("matrix entries must be finite numbers")
    if not math.isfinite(value):
        raise ValueError("matrix entries must be finite numbers")
    return float(value)


def _acted_sites(value: object, num_qubits: int, dim: int) -> list[int]:
    """Return a contiguous qubit range whose size matches ``dim``."""
    if not isinstance(value, list) or not value:
        raise ValueError("acted qubits must be a non-empty list")
    sites: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= num_qubits:
            raise ValueError(f"acted qubits must be indexes from 0 to {num_qubits - 1}")
        sites.append(item)
    if len(set(sites)) != len(sites):
        raise ValueError("acted qubits must be unique")
    ordered = sorted(sites)
    if ordered[-1] - ordered[0] + 1 != len(ordered):
        raise ValueError("acted qubits must be contiguous")
    if 2 ** len(ordered) != dim:
        expected = 2 ** len(ordered)
        raise ValueError(f"matrix must be {expected}×{expected} for {len(ordered)} acted qubits")
    return ordered


_REAL_TEXT = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$", re.IGNORECASE)
_EDGE_PAIR = re.compile(r"^(\d+)-(\d+)$")
_EDGE_PAREN = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


def _factory_kwargs(params: list[ListedParam], payload: object) -> dict[str, object]:
    """Return factory keyword arguments posted by the chip.

    A missing chip field keeps that default. An empty ``edges`` value is omitted
    so the chain preset stays in place. Integer fields are bound first. A
    per-emitter list then uses the bound ``n_emitters``, or length 1 when that
    argument was not posted.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("factory arguments must be an object")
    kwargs: dict[str, object] = {}
    for param in params:
        if param["kind"] != "integer":
            continue
        name = param["name"]
        if name not in payload or payload[name] is None:
            continue
        kwargs[name] = _factory_integer(name, payload[name], _integer_minimum(param))
    posted_emitters = kwargs.get("n_emitters")
    sequence_length = posted_emitters if isinstance(posted_emitters, int) else 1
    for param in params:
        if param["kind"] == "integer":
            continue
        name = param["name"]
        if name not in payload or payload[name] is None:
            continue
        kind = param["kind"]
        value = payload[name]
        if kind == "edges":
            edges = _factory_edges(value)
            if edges is None:
                continue
            kwargs[name] = edges
        elif kind == "choice":
            kwargs[name] = _factory_choice(name, param.get("choices"), value)
        elif kind == "number_or_list":
            kwargs[name] = _factory_sequence(name, value, sequence_length)
        else:
            kwargs[name] = _factory_real(name, value)
    return kwargs


def _integer_minimum(param: ListedParam) -> int:
    """Return the catalog minimum for an integer field."""
    minimum = param.get("minimum", 1)
    if isinstance(minimum, bool) or not isinstance(minimum, int):
        return 1
    return minimum


def _factory_integer(name: str, value: object, minimum: int) -> int:
    """Return an integer chip argument of at least ``minimum``."""
    try:
        number = _integer(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer of at least {minimum}") from None
    if number < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return number


def _factory_real(name: str, value: object) -> float:
    """Return one finite real chip argument."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a real number")
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if _REAL_TEXT.fullmatch(text) is None:
            raise ValueError(f"{name} must be a real number")
        number = float(text)
    else:
        raise ValueError(f"{name} must be a real number")
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a real number")
    return number


def _factory_sequence(name: str, value: object, n_emitters: int | None) -> float | list[float]:
    """Return a scalar or one number per emitter."""
    if isinstance(value, str) and "," in value:
        parts = [part.strip() for part in value.split(",")]
        if not parts or any(part == "" for part in parts):
            raise ValueError(f"{name} must be a real number")
        numbers = [_factory_real(name, part) for part in parts]
    elif isinstance(value, list):
        numbers = [_factory_real(name, item) for item in value]
    else:
        return _factory_real(name, value)
    if n_emitters is not None and len(numbers) != n_emitters:
        raise ValueError(f"{name} must be a scalar or a sequence of length {n_emitters}, got length {len(numbers)}")
    return numbers


def _factory_choice(name: str, choices: list[str] | None, value: object) -> str:
    """Return a chip choice that the factory accepts."""
    allowed = choices or []
    if isinstance(value, str) and value.strip() in allowed:
        return value.strip()
    rendered = ", ".join(allowed)
    raise ValueError(f"{name} must be one of {rendered}")


def _factory_edges(value: object) -> list[tuple[int, int]] | None:
    """Return posted edges. Blank text means the chain preset."""
    if isinstance(value, str):
        return _edge_text(value)
    if not isinstance(value, list):
        raise ValueError("edges must be pairs such as 0-1, 1-2")
    pairs: list[tuple[int, int]] = []
    for item in value:
        if (
            isinstance(item, list | tuple)
            and len(item) == 2
            and all(isinstance(part, int) and not isinstance(part, bool) for part in item)
        ):
            pairs.append((item[0], item[1]))
            continue
        raise ValueError("edges must be pairs such as 0-1, 1-2")
    return pairs


def _edge_text(text: str) -> list[tuple[int, int]] | None:
    """Parse ``0-1, 1-2`` or ``(0, 1), (1, 2)``."""
    trimmed = text.strip()
    if not trimmed:
        return None
    if "(" in trimmed or ")" in trimmed:
        pairs = [(int(left), int(right)) for left, right in _EDGE_PAREN.findall(trimmed)]
        rest = re.sub(r"[,\s]", "", _EDGE_PAREN.sub("", trimmed))
        if rest or not pairs:
            raise ValueError("edges must be pairs such as 0-1, 1-2")
        return pairs
    tokens = [token for token in re.split(r"[\s,]+", trimmed) if token]
    if not tokens:
        raise ValueError("edges must be pairs such as 0-1, 1-2")
    pairs = []
    for token in tokens:
        match = _EDGE_PAIR.fullmatch(token)
        if match is None:
            raise ValueError("edges must be pairs such as 0-1, 1-2")
        pairs.append((int(match.group(1)), int(match.group(2))))
    return pairs


def _factory_qubit_cap(build: object, parameters: Mapping[str, inspect.Parameter], bound: Mapping[str, object]) -> None:
    """Reject a reported qubit count above the page budget.

    A factory that takes ``n_qubits`` is capped where that argument is read.
    Any other factory must provide ``qubit_count`` so the layout can be rejected
    before the operators are built.
    """
    if "n_qubits" in parameters:
        return
    counter = getattr(build, "qubit_count", None)
    if not callable(counter):
        raise ValueError("model does not report a qubit count")
    kwargs = {name: bound[name] for name in inspect.signature(counter).parameters if name in bound}
    if counter(**kwargs) > _PAGE_QUBIT_CAP:
        raise ValueError(f"must use at most {_PAGE_QUBIT_CAP} qubits")


def _model(model_id: str, arguments: Mapping[str, object]) -> IsingModel | TavisCummingsModel:
    """Build the selected factory by binding ``arguments`` to its signature.

    ``n_qubits`` is read from the Qubits setting when the signature takes it.
    The other posted names are catalog fields and go through
    :func:`_factory_kwargs`. A factory that does not take ``n_qubits`` is capped
    from its ``qubit_count`` before it builds. A posted name the signature does
    not take fails. A missing chip field keeps the default.
    """
    record = next((item for item in listed_models() if item["id"] == model_id), None)
    if record is None:
        raise ValueError("unknown model")
    build = getattr(models, record["id"])
    parameters = inspect.signature(build).parameters
    chip_names = {param["name"] for param in record["params"]}
    if "n_qubits" in parameters:
        chip_names.add("n_qubits")
    unknown = [name for name in arguments if name not in chip_names]
    if unknown:
        raise ValueError(f"unknown argument {min(unknown)}")
    bound: dict[str, object] = {}
    if "n_qubits" in parameters:
        num_qubits = _integer(arguments.get("n_qubits"))
        if num_qubits > _PAGE_QUBIT_CAP:
            raise ValueError(f"qubits must be at most {_PAGE_QUBIT_CAP}")
        bound["n_qubits"] = num_qubits
    bound.update(_factory_kwargs(record["params"], arguments))
    _factory_qubit_cap(build, parameters, bound)
    return cast(IsingModel | TavisCummingsModel, build(**bound))


def _measure_sites(measure: Mapping[str, object], num_qubits: int) -> list[int]:
    """Return qubit indexes to measure. Missing ``sites`` means every qubit."""
    raw = measure.get("sites")
    if raw is None:
        return list(range(num_qubits))
    if not isinstance(raw, list) or not raw:
        raise ValueError("measured qubits must be a non-empty list of indexes")
    sites: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= num_qubits:
            raise ValueError(f"measured qubits must be indexes from 0 to {num_qubits - 1}")
        if item not in sites:
            sites.append(item)
    return sites


def _require_measure(model: _PageModel, measure_id: str) -> None:
    """Reject a measurement that does not belong to ``model``.

    ``model`` records the factory's own measurements. An added Hamiltonian
    records a catalog measurement. A factory whose observable list and
    measurement list differ in length cannot be recorded.

    Raises:
        ValueError: The id belongs to the other kind of model, or the factory
            lists do not match.
    """
    if measure_id == "model":
        if isinstance(model, _AddedModel):
            raise ValueError("an added Hamiltonian measures X, Y, Z, or a counts expression")
        _model_records(model)
        return
    if not isinstance(model, _AddedModel):
        raise ValueError("a preexisting model records its own measurements")


def _model_records(model: _FactoryModel) -> tuple[list[Operator], list[Measurement]]:
    """Return ``e_ops`` and ``measurements`` when the two lists have the same length.

    Raises:
        ValueError: The factory lists differ in length.
    """
    if len(model.e_ops) != len(model.measurements):
        raise ValueError("model measurements do not match its observables")
    return list(model.e_ops), list(model.measurements)


def _page_measurements(model: _PageModel, measure: Mapping[str, object]) -> list[Measurement]:
    """Return the measurements a circuit simulator reads after it runs.

    Raises:
        ValueError: ``measure`` does not belong to ``model``, or a counts
            expression is not allowed.
    """
    measure_id = _text(measure.get("id"))
    _require_measure(model, measure_id)
    if measure_id == "model":
        return _model_records(cast(_FactoryModel, model))[1]
    return _measurements(measure, model.num_qubits)


def _chart_labels(model: _PageModel, measure: Mapping[str, object]) -> list[str]:
    """Return one chart name per recorded curve."""
    if _text(measure.get("id")) == "model":
        return [item.label for item in _model_records(cast(_FactoryModel, model))[1]]
    return _observable_labels(measure, model.num_qubits)


def _measurements(measure: Mapping[str, object], num_qubits: int) -> list[Measurement]:
    """Return the page measurements: one expectation per selected qubit, or one counts expression.

    Raises:
        ValueError: ``measure`` is unknown, or the counts ``expression`` is not allowed.
    """
    return measurements_for(measure, num_qubits)


def _observable_labels(measure: Mapping[str, object], num_qubits: int) -> list[str]:
    """Return one chart name per curve.

    A Pauli measurement on qubits 0 and 1 is ``⟨Z⟩ on 0`` and ``⟨Z⟩ on 1``, using
    that record's letter. ``counts`` is its expression.
    """
    return labels_for(measure, num_qubits)


def _observables(num_qubits: int, measure_id: str, sites: list[int]) -> list[Operator]:
    """Return one Pauli on each selected qubit for a Pauli ``measure_id``."""
    return observables_for(num_qubits, measure_id, sites)


def _initial_state(state_id: str, num_qubits: int, data: object = None) -> State:
    """Prepare ``state_id`` on ``num_qubits`` qubits from the posted ``data``."""
    return prepare_state(state_id, num_qubits, data)
