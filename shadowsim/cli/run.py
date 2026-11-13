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
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.encoding.amplitude import AmplitudeEncoding
from shadowsim.encoding.angle import AngleEncoding
from shadowsim.encoding.computational_basis import ComputationalBasisEncoding
from shadowsim.encoding.gray import GrayEncoding
from shadowsim.models.catalog import ListedParam, listed_models
from shadowsim.models.ising import IsingModel
from shadowsim.models.tavis_cummings import TavisCummingsModel
from shadowsim.simulators.reducers import Measurement
from shadowsim.simulators.result import SimulationResult, _resource_record, save_resource_metrics
from shadowsim.simulators.simulator import Simulator
from shadowsim.utils.hermitian import hermitian

_STATES = frozenset({"basis", "gray", "angle", "amplitude"})
# A page click cannot afford the class defaults of 101 points and 10_000 shots.
_CIRCUIT_TIME_STEPS = 11
_CIRCUIT_NUM_STEPS = 4
_CIRCUIT_SHOTS = 256
_CIRCUIT_SEED = 0
_DEFAULT_SAVE_PATH = "results/run1"
_DEFAULT_EXPORT_DIR = "results"
_MAX_OPERATOR_QUBITS = 8
_MAX_FACTORY_QUBITS = 15
_MAX_TIME_STEPS = 500
_MAX_NUM_STEPS = 100
_MAX_TROTTER_DEPTH = 100
_MAX_SHOTS = 100000


@dataclass(frozen=True)
class _AddedModel:
    """Operators posted from the Add cards."""

    num_qubits: int
    full_hamiltonians: list[Hamiltonian]
    local_hamiltonians: list[LocalHamiltonian]
    c_ops_full: list[Operator]
    c_ops_local: list[LocalOperator]


_PageModel = IsingModel | TavisCummingsModel | _AddedModel

_RUN_VERSION = 1
_DOCUMENT_KEYS = frozenset({"version", "total", "state", "model", "simulators", "measure", "actions"})
_MODEL_KEYS = frozenset({"id", "arguments", "terms", "qubits"})
_MEASURE_KEYS = frozenset({"id", "sites", "expression"})
_ACTION_KEYS = frozenset({"ids", "save_path", "export_path"})
_ENTRY_KEYS = frozenset({"id", "arguments", "backend"})
_BACKEND_KEYS = frozenset({"id", "arguments"})
_STATE_KEYS = frozenset({"id", "value"})
# Structural names ``_model`` reads beside the chip fields.
_STRUCTURAL_ARGUMENTS = frozenset({"n_qubits", "n_emitters", "n_cavities", "nu"})


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
            ``backend`` (null, or ``id`` plus ``arguments``). ``measure`` has
            ``id`` and ``sites``, plus ``expression`` for ``counts``. ``actions``
            is ignored. The simulator ``id`` is
            an id from :func:`shadowsim.simulators.catalog.listed_simulators`.
            A simulator that records observables ignores a missing backend. A
            circuit simulator's ``backend`` is an id from
            :func:`shadowsim.backends.catalog.listed_backends`, and one that
            samples needs a backend with a shot budget. ``measure`` of ``x`` or
            ``z`` records that Pauli's expectation on each selected qubit for
            every simulator. ``counts`` evaluates ``expression`` (see
            :class:`~shadowsim.simulators.Measurement`) on the shot counts of the
            selected qubits, in ``sites`` order. It needs a backend with a shot
            budget, so an observables simulator and a backend without one reject
            it. A circuit simulator records counts only; :func:`run_page` reads them.
            ``model`` is a factory name from :func:`shadowsim.models.catalog.listed_models`.
            A non-empty ``terms`` list is the model instead: each item has ``id``
            and ``matrix``, and local terms also have ``sites``. At least one
            Hamiltonian term is required.
            Factory ``arguments`` use the factory's parameter names. A posted
            name the factory does not take fails. ``n_qubits`` is at most 15.
            Tavis–Cummings reads ``n_emitters`` (1 to 13, default 1) and uses
            ``2 + n_emitters`` qubits. Tavis–Cummings–Hubbard reads
            ``n_cavities`` (default 1), ``n_emitters`` (1 to 13, default 1), and
            real ``nu`` (default 0). Its qubit count is ``n_cavities * (2 +
            n_emitters)``, at most 15. Jaynes–Cummings–Hubbard reads
            ``n_cavities`` and real ``nu``, with one emitter per cavity, so its
            qubit count is ``3 * n_cavities``, at most 15. Jaynes–Cummings is 3
            qubits. The other arguments are the chip fields. A missing chip
            field keeps that model's default.
            Numbers are finite reals or numeric text. A per-emitter value is a
            scalar or a sequence whose length is the emitter count. ``edges`` is
            empty, dash pairs such as ``0-1, 1-2``, or a list of pairs.
            ``state.value`` is the payload for ``state.id``. A basis or Gray code
            is a string of 0 and 1 whose length is the qubit count, at most 15
            characters. Angle is one finite real number per qubit. Amplitude is
            a non-zero list of finite real numbers, and the padded vector must
            use the model's qubit count. ``measure.sites`` lists qubit indexes
            to measure. Missing ``sites`` measures every qubit.
            ``time_steps`` in the simulator arguments must be from 1 to 500.
            Missing ``time_steps`` uses 101 for an observables simulator and 11
            for a circuit simulator. Shot-based simulators also read
            ``num_steps`` (1 to 100), ``trotter_depth`` (1 to 100), ``order`` (1 or
            2), and ``seed`` from those arguments. A backend with a shot budget
            reads ``shots`` (1 to 100000) from the backend arguments. A posted
            ``time_steps`` value is checked before the simulator extra is
            imported. A posted ``shots`` value is checked then too when that
            backend has a shot budget, and also when no backend module can be
            imported. A gate-list field, such as Aer's ``basis_gates``, is a
            comma-separated string or a sequence of names. A blank value keeps
            that backend's own basis. Any other backend field is a non-negative
            number, and a missing value keeps the catalog default. A simulator
            with ``closed_system`` set rejects Lindblad operators. Missing
            shot-based values use the page budget.
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
    if document.state_id not in _STATES:
        raise ValueError("unknown initial state")
    total_time = _positive_number(document.total)
    model = _page_model(document.model)
    state = _initial_state(document.state_id, model.num_qubits, document.state_value)
    measure_id = _text(document.measure.get("id"))
    sites = _measure_sites(document.measure, model.num_qubits)
    _measurements(document.measure, model.num_qubits)
    if class_name == "QutipSimulator":
        _reject_counts(measure_id, "QuTiP")
        steps = _selection_positive_int(entry.arguments, "time_steps", 101, "time steps", maximum=_MAX_TIME_STEPS)
        return _qutip_simulator(model, state, measure_id, total_time, steps, sites)
    if "time_steps" in entry.arguments:
        _selection_positive_int(entry.arguments, "time_steps", 101, "time steps", maximum=_MAX_TIME_STEPS)
    if backend and "shots" in entry.backend_arguments and _backend_has_shot_budget(backend):
        _selection_positive_int(entry.backend_arguments, "shots", _CIRCUIT_SHOTS, "shots", maximum=_MAX_SHOTS)
    cls = _load_exported(module_name, extra, class_name, "unknown simulator")
    if "observables" in inspect.signature(cls).parameters:
        _reject_counts(measure_id, class_name.removesuffix("Simulator"))
        steps = _selection_positive_int(entry.arguments, "time_steps", 101, "time steps", maximum=_MAX_TIME_STEPS)
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


def run_page(selection: Mapping[str, object], *, output_root: Path | None = None) -> dict[str, object]:
    """Run every simulator in a version 1 document.

    One ``simulators`` entry is one simulation. Two or more is a benchmark.
    The first entry is the reference. Any exported simulator may be the reference
    or a challenger. Every entry must share ``total`` and ``time_steps``, because
    :class:`~shadowsim.benchmarking.benchmark.Benchmark` compares one time grid.
    ``time_steps`` is read from that entry's arguments. ``actions`` lists the
    ids to run. ``save`` writes each
    result under ``save_path``, or ``results/run1`` when that key is missing.
    One result is the directory itself. A benchmark writes ``sim_1``,
    ``sim_2``, and so on inside it. ``export`` writes metrics JSON under
    ``export_path``, or ``results/`` when that key is missing. A benchmark uses
    :meth:`~shadowsim.benchmarking.benchmark.Benchmark.save_error_metrics`.
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
    document = _read_document(selection)
    directory = _save_directory(document, output_root)
    export_to = _export_location(document, output_root)
    if len(document.simulators) >= 2:
        return _run_benchmark(selection, document, directory, export_to)
    simulator = _build_simulator(document, 0)
    simulator.simulate()
    result = _measured_result(simulator, selection)
    payload = _result_payload(result, simulator, document.measure)
    saved = _write_results(directory, [result])
    if saved:
        payload["saved"] = saved
    exported = _export_resources(export_to, simulator, result.runtime)
    if exported:
        payload["exported"] = exported
    return payload


def _measured_result(simulator: Simulator, selection: Mapping[str, object]) -> SimulationResult:
    """Read the page measurements from a simulated circuit simulator and return its result.

    QuTiP already records its Pauli expectations, so its result is returned unchanged.

    Raises:
        ValueError: ``simulator`` has not been simulated, or the measurement
            cannot be read from its result.
    """
    document = _read_document(selection)
    if getattr(simulator, "circuit_backend", None) is None:
        if simulator.last_result is None:
            raise ValueError("Results are not available. Please run the simulation first.")
        return simulator.last_result
    return simulator.measure(_measurements(document.measure, simulator.num_qubits))


def _result_payload(
    result: SimulationResult,
    simulator: Simulator,
    measure: Mapping[str, object],
) -> dict[str, object]:
    """Return the curves, names, and resource record the page chart draws."""
    return {
        "times": result.times.tolist(),
        "observables": [curve.tolist() for curve in result.observables],
        "labels": _observable_labels(measure, simulator.num_qubits),
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


def _save_directory(document: _RunDocument, output_root: Path | None) -> Path | None:
    """Return the save directory, or ``None`` when this run is not saved.

    Raises:
        ValueError: ``save`` is selected and ``save_path`` is not a path, or it
            resolves outside ``output_root``.
    """
    if "save" not in document.action_ids:
        return None
    raw = document.actions.get("save_path", _DEFAULT_SAVE_PATH)
    if raw is None:
        raw = _DEFAULT_SAVE_PATH
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
    raw = document.actions.get("export_path", _DEFAULT_EXPORT_DIR)
    if raw is None:
        raw = _DEFAULT_EXPORT_DIR
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


def _series_name(report_id: str) -> str:
    """Return a chart name, with ``_simulator`` removed before any ``#n`` suffix."""
    base, separator, number = report_id.partition("#")
    short = base.removesuffix("_simulator")
    if separator:
        return f"{short}#{number}"
    return short


def _run_benchmark(
    selection: Mapping[str, object],
    document: _RunDocument,
    directory: Path | None,
    export_to: Path | None,
) -> dict[str, object]:
    """Build each entry, run them on one grid, and return curves, names, and resources."""
    simulators = [_build_simulator(document, index) for index in range(len(document.simulators))]
    benchmark = Benchmark(simulators[0], *simulators[1:])
    benchmark.run()
    recorded = [_measured_result(simulator, selection) for simulator in simulators]
    resources = benchmark.resource_metrics()
    labels = _observable_labels(document.measure, simulators[0].num_qubits)
    series: list[dict[str, object]] = []
    for result, resource in zip(recorded, resources, strict=True):
        name = _series_name(str(resource["simulator_id"]))
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
    saved = _write_results(directory, [item.last_result for item in simulators if item.last_result is not None])
    if saved:
        payload["saved"] = saved
    exported = _export_benchmark(export_to, benchmark)
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
    """Build an observables simulator for explicit Pauli observables.

    QuTiP is imported when ``cls`` is omitted, so a test can replace this
    function without importing that extra.
    """
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

    X rotates the selected qubits into the X basis before the measurement. Z
    and counts measure every qubit in Z. The simulator records counts, or Pauli
    expectations when the backend has no shot budget, which
    :func:`_measured_result` reads.
    """
    steps = _selection_positive_int(arguments, "time_steps", _CIRCUIT_TIME_STEPS, "time steps", maximum=_MAX_TIME_STEPS)
    num_steps = _selection_positive_int(
        arguments, "num_steps", _CIRCUIT_NUM_STEPS, "product steps", maximum=_MAX_NUM_STEPS
    )
    seed = _selection_integer(arguments, "seed", _CIRCUIT_SEED, "seed")
    if getattr(cls, "closed_system", False) and model.c_ops_local:
        raise ValueError(f"{cls.__name__.removesuffix('Simulator')} is closed-system only")
    circuit_backend = _make_backend(record, backend_arguments)
    # Trotter depth and order are constructor arguments only for product-formula simulators.
    extra: dict[str, Any] = {}
    if "trotter_depth" in inspect.signature(cls).parameters:
        extra["trotter_depth"] = _selection_positive_int(
            arguments, "trotter_depth", 1, "Trotter depth", maximum=_MAX_TROTTER_DEPTH
        )
        extra["order"] = _selection_order(arguments)
    if measure_id == "x":
        extra["basis"] = _x_basis(model.num_qubits, sites)
    return cls(
        model.local_hamiltonians,
        model.c_ops_local,
        state,
        num_qubits=model.num_qubits,
        total_time=total_time,
        time_steps=steps,
        num_steps=num_steps,
        seed=seed,
        circuit_backend=circuit_backend,
        **extra,
    )


def _reject_counts(measure_id: str, label: str) -> None:
    """Reject a counts measurement for a simulator or backend that returns expectations."""
    if measure_id != "counts":
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


def _x_basis(num_qubits: int, sites: list[int]) -> str:
    """Return a basis that reads X on ``sites`` and Z on every other qubit."""
    return "".join("X" if qubit in sites else "Z" for qubit in range(num_qubits))


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


def _selection_order(selection: Mapping[str, object]) -> int:
    """Return Trotter order 1 or 2. Missing ``order`` means 1."""
    if "order" not in selection:
        return 1
    number = _named_integer(selection["order"], "order")
    if number not in (1, 2):
        raise ValueError("order must be 1 or 2")
    return number


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
        raise ValueError("qubits must be from 1 to 8")
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
    """Return a square complex matrix of size 2, 4, ..., 256."""
    if not isinstance(value, list) or not value or any(not isinstance(row, list) for row in value):
        raise ValueError("matrix must be a square 2D array")
    rows = [[_complex_entry(entry) for entry in row] for row in value]
    size = len(rows)
    if any(len(row) != size for row in rows):
        raise ValueError("matrix must be a square 2D array")
    if size < 2 or size > 2**_MAX_OPERATOR_QUBITS or size & (size - 1) != 0:
        raise ValueError("matrix size must be a power of two from 2 to 256")
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


def _emitter_count(value: object) -> int:
    """Return an emitter count from 1 to 13. A missing value is 1."""
    if value is None:
        return 1
    try:
        count = _integer(value)
    except ValueError:
        raise ValueError("emitters must be an integer from 1 to 13") from None
    if count < 1 or count > 13:
        raise ValueError("emitters must be an integer from 1 to 13")
    return count


def _cavity_count(value: object) -> int:
    """Return a cavity count of at least 1. A missing value is 1."""
    if value is None:
        return 1
    try:
        count = _integer(value)
    except ValueError:
        raise ValueError("cavities must be an integer of at least 1") from None
    if count < 1:
        raise ValueError("cavities must be an integer of at least 1")
    return count


def _hopping(value: object) -> float:
    """Return a finite real hopping strength. A missing value is 0."""
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("hopping must be a real number")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("hopping must be a real number")
        try:
            number = float(text)
        except ValueError:
            raise ValueError("hopping must be a real number") from None
    else:
        number = float(value)
    if not math.isfinite(number):
        raise ValueError("hopping must be a real number")
    return number


_REAL_TEXT = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$", re.IGNORECASE)
_EDGE_PAIR = re.compile(r"^(\d+)-(\d+)$")
_EDGE_PAREN = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


def _factory_kwargs(params: list[ListedParam], payload: object, *, n_emitters: int | None) -> dict[str, object]:
    """Return factory keyword arguments posted by the chip.

    A missing chip field keeps that default. An empty ``edges`` value is omitted
    so the chain preset stays in place.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("factory arguments must be an object")
    kwargs: dict[str, object] = {}
    for param in params:
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
            kwargs[name] = _factory_sequence(name, value, n_emitters)
        else:
            kwargs[name] = _factory_real(name, value)
    return kwargs


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


def _factory_qubit_budget(
    parameters: Mapping[str, inspect.Parameter],
    *,
    n_emitters: int | None,
    n_cavities: int | None,
) -> None:
    """Reject a layout whose qubit count is above the page budget.

    ``n_qubits`` is capped where it is read. Both cavity and emitter counts use
    ``n_cavities * (2 + n_emitters)``. Cavities alone use ``3 * n_cavities``.
    Emitters alone are already at most 13, and a factory with neither is 3 qubits.
    """
    if "n_qubits" in parameters or n_cavities is None:
        return
    if n_emitters is not None and n_cavities * (2 + n_emitters) > _MAX_FACTORY_QUBITS:
        raise ValueError(f"cavities and emitters must use at most {_MAX_FACTORY_QUBITS} qubits")
    if n_emitters is None and n_cavities * 3 > _MAX_FACTORY_QUBITS:
        raise ValueError(f"cavities must use at most {_MAX_FACTORY_QUBITS} qubits")


def _model(model_id: str, arguments: Mapping[str, object]) -> IsingModel | TavisCummingsModel:
    """Build the selected factory by binding ``arguments`` to its signature.

    ``n_qubits``, ``n_emitters``, ``n_cavities``, and ``nu`` use the page
    coercers when the signature has those names. Chip fields go through
    :func:`_factory_kwargs`, and a list-valued field uses the bound emitter
    count, or length 1 when the signature has no ``n_emitters``. A posted name
    the signature does not take fails. A missing chip field keeps the default.
    """
    record = next((item for item in listed_models() if item["id"] == model_id), None)
    if record is None:
        raise ValueError("unknown model")
    build = getattr(models, record["id"])
    parameters = inspect.signature(build).parameters
    structural = _STRUCTURAL_ARGUMENTS.intersection(parameters)
    chip_names = {param["name"] for param in record["params"]}
    unknown = [name for name in arguments if name not in structural and name not in chip_names]
    if unknown:
        raise ValueError(f"unknown argument {min(unknown)}")
    bound: dict[str, object] = {}
    n_emitters: int | None = None
    n_cavities: int | None = None
    if "n_qubits" in parameters:
        num_qubits = _integer(arguments.get("n_qubits"))
        if num_qubits > _MAX_FACTORY_QUBITS:
            raise ValueError(f"qubits must be at most {_MAX_FACTORY_QUBITS}")
        bound["n_qubits"] = num_qubits
    if "n_emitters" in parameters:
        n_emitters = _emitter_count(arguments.get("n_emitters"))
        bound["n_emitters"] = n_emitters
    if "n_cavities" in parameters:
        n_cavities = _cavity_count(arguments.get("n_cavities"))
        bound["n_cavities"] = n_cavities
    _factory_qubit_budget(parameters, n_emitters=n_emitters, n_cavities=n_cavities)
    sequence_length = n_emitters if n_emitters is not None else 1
    bound.update(_factory_kwargs(record["params"], arguments, n_emitters=sequence_length))
    if "nu" in parameters:
        bound["nu"] = _hopping(arguments.get("nu"))
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


def _measurements(measure: Mapping[str, object], num_qubits: int) -> list[Measurement]:
    """Return the page measurements: one expectation per selected qubit, or one counts expression.

    Raises:
        ValueError: ``measure`` is unknown, or the counts ``expression`` is not allowed.
    """
    measure_id = _text(measure.get("id"))
    sites = _measure_sites(measure, num_qubits)
    if measure_id in ("x", "z"):
        return [Measurement.expectation(site) for site in sites]
    if measure_id != "counts":
        raise ValueError("unknown measurement")
    expression = measure.get("expression")
    if not isinstance(expression, str):
        raise ValueError("a counts measurement needs an expression")
    return [Measurement(tuple(sites), expression)]


def _observable_labels(measure: Mapping[str, object], num_qubits: int) -> list[str]:
    """Return one chart name per curve.

    ``z`` on qubits 0 and 1 is ``⟨Z⟩ on 0`` and ``⟨Z⟩ on 1``. ``counts`` is its expression.
    """
    measure_id = _text(measure.get("id"))
    if measure_id == "counts":
        return [item.label for item in _measurements(measure, num_qubits)]
    if measure_id not in ("x", "z"):
        raise ValueError("unknown measurement")
    letter = measure_id.upper()
    return [f"⟨{letter}⟩ on {site}" for site in _measure_sites(measure, num_qubits)]


def _observables(num_qubits: int, measure_id: str, sites: list[int]) -> list[Operator]:
    """Return one Pauli on each selected qubit for ``measure_id``, which is ``x`` or ``z``."""
    letter = measure_id.upper()
    observables: list[Operator] = []
    for site in sites:
        label = ["I"] * num_qubits
        label[site] = letter
        observables.append(Operator("".join(label)))
    return observables


def _bit_string(value: object, label: str) -> list[int]:
    """Return ``value`` as bits when it is a string of 0 and 1, at most 15 characters."""
    if not isinstance(value, str) or not value or len(value) > 15 or any(bit not in "01" for bit in value):
        raise ValueError(f"{label} must be a string of 0 and 1, at most 15 characters")
    return [int(bit) for bit in value]


def _real_list(value: object, count: int | None, label: str) -> list[float]:
    """Return ``value`` as finite real numbers, and require ``count`` of them when set."""
    expected = f"{count} finite real numbers" if count is not None else "a non-empty list of finite real numbers"
    if not isinstance(value, list) or not value or (count is not None and len(value) != count):
        raise ValueError(f"{label} must be {expected}")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise ValueError(f"{label} must be {expected}")
        numbers.append(float(item))
    return numbers


def _initial_state(state_id: str, num_qubits: int, data: object = None) -> State:
    """Prepare ``state_id`` on ``num_qubits`` qubits from the posted ``data``."""
    if state_id == "basis":
        bits = _bit_string(data, "basis bits")
        if len(bits) != num_qubits:
            raise ValueError(f"basis bit string length must equal the qubit count ({num_qubits})")
        return ComputationalBasisEncoding(num_qubits).encode(bits)
    if state_id == "gray":
        bits = _bit_string(data, "Gray code bits")
        if len(bits) != num_qubits:
            raise ValueError(f"Gray code bit string length must equal the qubit count ({num_qubits})")
        return GrayEncoding(num_qubits).encode(bits)
    if state_id == "angle":
        return AngleEncoding().encode(_real_list(data, num_qubits, "angles"))
    if state_id != "amplitude":
        raise ValueError("unknown initial state")
    state = AmplitudeEncoding().encode(_real_list(data, None, "amplitudes"))
    prepared = state.get_num_qubits()
    if prepared != num_qubits:
        prepared_label = "qubit" if prepared == 1 else "qubits"
        model_label = "qubit" if num_qubits == 1 else "qubits"
        raise ValueError(
            f"amplitude encoding prepares {prepared} {prepared_label}, model has {num_qubits} {model_label}"
        )
    return state
