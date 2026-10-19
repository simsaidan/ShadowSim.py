"""Build a simulator from a builder-page selection."""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy as np

from shadowsim import models
from shadowsim._optional import import_optional
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
from shadowsim.models.catalog import listed_models
from shadowsim.models.ising import IsingModel
from shadowsim.models.tavis_cummings import TavisCummingsModel
from shadowsim.simulators.reducers import expectation_x, expectation_z
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.utils.hermitian import hermitian

_STATES = frozenset({"basis", "gray", "angle", "amplitude"})
_SIMULATORS = frozenset({"qutip", "trotterization", "splitjmatrix"})
# A page click cannot afford the class defaults of 101 points and 10_000 shots.
_CIRCUIT_TIME_STEPS = 11
_CIRCUIT_NUM_STEPS = 4
_CIRCUIT_SHOTS = 256
_CIRCUIT_SEED = 0
_DEFAULT_SAVE_PATH = "results/run1"
_DEFAULT_EXPORT_DIR = "results"
_MAX_OPERATOR_QUBITS = 8


@dataclass(frozen=True)
class _AddedModel:
    """Operators posted from the Add cards."""

    num_qubits: int
    full_hamiltonians: list[Hamiltonian]
    local_hamiltonians: list[LocalHamiltonian]
    c_ops_full: list[Operator]
    c_ops_local: list[LocalOperator]


_PageModel = IsingModel | TavisCummingsModel | _AddedModel


def build_simulator(selection: Mapping[str, object], *, time_steps: int = 101) -> Simulator:
    """Build a simulator for one builder-page selection.

    Args:
        selection: Page ids and settings. ``then`` is ignored. ``backend`` must
            be ``aer``. ``measure`` of ``x`` or ``z`` records that Pauli's
            expectation on each selected qubit for every simulator.
            ``model`` is a factory name from :func:`shadowsim.models.catalog.listed_models`.
            A non-empty ``terms`` list is the model instead: each item has ``id``
            and ``matrix``, and local terms also have ``sites``. At least one
            Hamiltonian term is required.
            Factories that require ``n_qubits`` read ``qubits``. Jaynes–Cummings is
            always 3 qubits and ignores ``qubits``. Tavis–Cummings reads
            ``emitters`` (1 to 13, default 1) and uses ``2 + emitters`` qubits.
            A basis or Gray code state reads ``basis`` or ``gray``, a string of 0
            and 1 whose length is the qubit count, at most 15 characters. Angle
            reads ``angles``, one finite real number per qubit. Amplitude reads
            ``amplitudes``, a non-zero list of finite real numbers, and the
            padded vector must use the model's qubit count.
            ``sites`` lists qubit indexes to measure. Missing ``sites`` measures
            every qubit.
            ``time_steps`` in ``selection`` overrides the ``time_steps`` argument.
            Shot-based simulators also read ``num_steps``, ``trotter_depth``,
            ``shots``, and ``seed``. ``shots`` is shared by those simulators; the
            page collects it on the backend. Trotterization reads ``order``, which
            is 1 or 2.
            Missing shot-based values use the page budget.
        time_steps: Points on the QuTiP solver grid when ``selection`` omits
            ``time_steps``. Defaults to the page preview.

    Returns:
        A simulator that has not been run.

    Raises:
        ValueError: The selection cannot run in this slice.
        ImportError: The QuTiP or Qiskit extra required by the simulator is not installed.
    """
    if isinstance(time_steps, bool) or not isinstance(time_steps, int) or time_steps < 1:
        raise ValueError("time_steps must be a positive integer")
    simulator_id = _choice(selection, "simulator")
    if simulator_id not in _SIMULATORS:
        raise ValueError("unknown simulator")
    backend = _choice(selection, "backend")
    if backend != "aer":
        raise ValueError("only Aer can run from the page")
    state_id = _choice(selection, "state")
    if state_id not in _STATES:
        raise ValueError("unknown initial state")
    total_time = _positive_number(selection.get("total"))
    terms = selection.get("terms")
    model: _PageModel
    if isinstance(terms, list) and terms:
        model = _added_model(terms, selection.get("qubits"))
    else:
        model = _model(_choice(selection, "model"), selection.get("qubits"), selection.get("emitters"))
    state = _initial_state(state_id, model.num_qubits, _state_data(selection, state_id))
    measure_id = _choice(selection, "measure")
    sites = _measure_sites(selection, model.num_qubits)
    if simulator_id == "qutip":
        steps = _selection_positive_int(selection, "time_steps", time_steps, "time steps")
        return _qutip_simulator(model, state, measure_id, total_time, steps, sites)
    return _circuit_simulator(simulator_id, selection, model, state, measure_id, total_time, sites)


def run_page(selection: Mapping[str, object]) -> dict[str, object]:
    """Run one selection, or a benchmark when ``simulators`` lists two or more.

    The first entry is the reference. Any exported simulator may be the reference
    or a challenger. Every entry must share ``total`` and ``time_steps``, because
    :class:`~shadowsim.benchmarking.benchmark.Benchmark` compares one time grid.
    A missing or shorter list runs the flat ``simulator`` field as one simulation.
    ``then`` is one action, or ``thens`` lists several. ``save`` writes each
    result under ``save_path``, or ``results/run1`` when that key is missing.
    One result is the directory itself. A benchmark writes ``sim_1``,
    ``sim_2``, and so on inside it. ``export`` writes metrics JSON under
    ``export_path``, or ``results/`` when that key is missing. A benchmark uses
    :meth:`~shadowsim.benchmarking.benchmark.Benchmark.save_error_metrics`.
    One simulator writes its runtime and shot budget. ``plot`` is drawn by the
    page. Save and export both run when both are selected.
    """
    directory = _save_directory(selection)
    export_to = _export_location(selection)
    entries = selection.get("simulators")
    if isinstance(entries, list) and len(entries) >= 2:
        return _run_benchmark(selection, entries, directory, export_to)
    simulator = build_simulator(selection)
    result = simulator.simulate()
    payload = _result_payload(result)
    saved = _write_results(directory, [result])
    if saved:
        payload["saved"] = saved
    exported = _export_resources(export_to, simulator, result.runtime)
    if exported:
        payload["exported"] = exported
    return payload


def _result_payload(result: SimulationResult) -> dict[str, object]:
    """Return the curves and timing the page chart draws."""
    return {
        "times": result.times.tolist(),
        "observables": [curve.tolist() for curve in result.observables],
        "runtime": result.runtime,
        "algorithm": result.algorithm,
    }


def _then_actions(selection: Mapping[str, object]) -> frozenset[str]:
    """Return the selected result actions. ``thens`` wins over a single ``then``."""
    raw = selection.get("thens")
    if raw is None:
        raw = selection.get("then")
    if isinstance(raw, str):
        return frozenset({raw})
    if isinstance(raw, list):
        return frozenset(item for item in raw if isinstance(item, str))
    return frozenset()


def _save_directory(selection: Mapping[str, object]) -> Path | None:
    """Return the save directory, or ``None`` when this run is not saved.

    Raises:
        ValueError: ``save`` is selected and ``save_path`` is not a path.
    """
    if "save" not in _then_actions(selection):
        return None
    raw = selection.get("save_path", _DEFAULT_SAVE_PATH)
    if raw is None:
        raw = _DEFAULT_SAVE_PATH
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("save path must be a path")
    return Path(raw.strip())


def _export_location(selection: Mapping[str, object]) -> Path | None:
    """Return where to write metrics JSON, or ``None`` when this run is not exported.

    Raises:
        ValueError: ``export`` is selected and ``export_path`` is not a path.
    """
    if "export" not in _then_actions(selection):
        return None
    raw = selection.get("export_path", _DEFAULT_EXPORT_DIR)
    if raw is None:
        raw = _DEFAULT_EXPORT_DIR
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("export path must be a path")
    return Path(raw.strip())


def _resource_record(simulator: Simulator, wall_time: float | None) -> dict[str, object]:
    """Return one simulator's runtime and shot budget."""
    shots_per_job = getattr(simulator, "shots", None)
    if isinstance(shots_per_job, bool) or not isinstance(shots_per_job, int):
        num_jobs = None
        total_shots = None
        shots_per_job = None
    else:
        num_jobs = len(simulator.tlist)
        total_shots = shots_per_job * num_jobs
    return {
        "simulator_id": simulator.id,
        "wall_time_s": wall_time,
        "shots_per_job": shots_per_job,
        "num_jobs": num_jobs,
        "total_shots": total_shots,
    }


def _export_resources(location: Path | None, simulator: Simulator, wall_time: float | None) -> str | None:
    """Write one simulator's runtime and shot budget. A ``.json`` path is that file."""
    if location is None:
        return None
    payload = {"resources": [_resource_record(simulator, wall_time)]}
    if location.suffix == ".json":
        path = location
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = location / f"resource_metrics_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return str(path)


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
    entries: list[object],
    directory: Path | None,
    export_to: Path | None,
) -> dict[str, object]:
    """Build each entry, run them on one grid, and return curves plus error metrics."""
    simulators: list[Simulator] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("each simulator must be an object")
        merged = dict(selection)
        merged.update(entry)
        simulators.append(build_simulator(merged))
    benchmark = Benchmark(simulators[0], *simulators[1:])
    benchmark.run()
    series: list[dict[str, object]] = []
    for simulator in simulators:
        result = simulator.last_result
        if result is None:
            raise ValueError("benchmark did not record a result")
        series.append(
            {
                "name": simulator.id.removesuffix("_simulator"),
                "observables": [curve.tolist() for curve in result.observables],
            }
        )
    reference = simulators[0].last_result
    assert reference is not None
    wall_times = [item["wall_time_s"] for item in benchmark.resource_metrics()]
    payload: dict[str, object] = {
        "times": reference.times.tolist(),
        "observables": [curve.tolist() for curve in reference.observables],
        "series": series,
        "errors": benchmark.error_metrics(),
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
) -> Simulator:
    """Build the QuTiP simulator for explicit Pauli observables."""
    observables = _observables(model.num_qubits, measure_id, sites)
    qutip_simulator = import_optional("shadowsim.simulators.qutip_simulator", extra="qutip")
    return qutip_simulator.QutipSimulator(
        model.full_hamiltonians,
        model.c_ops_full,
        state,
        observables,
        num_qubits=model.num_qubits,
        total_time=total_time,
        time_steps=time_steps,
    )


def _circuit_simulator(
    simulator_id: str,
    selection: Mapping[str, object],
    model: _PageModel,
    state: State,
    measure_id: str,
    total_time: float,
    sites: list[int],
) -> Simulator:
    """Build a shot-based simulator on Aer.

    Z and X each record that Pauli's expectation on every selected qubit.
    X is measured by rotating those qubits into the X basis first. Split J
    measures an ancilla first, so those qubit indexes shift by one.
    """
    if measure_id not in ("x", "z"):
        raise ValueError("unknown measurement")
    steps = _selection_positive_int(selection, "time_steps", _CIRCUIT_TIME_STEPS, "time steps")
    num_steps = _selection_positive_int(selection, "num_steps", _CIRCUIT_NUM_STEPS, "product steps")
    depth = _selection_positive_int(selection, "trotter_depth", 1, "Trotter depth")
    shots = _selection_positive_int(selection, "shots", _CIRCUIT_SHOTS, "shots")
    seed = _selection_integer(selection, "seed", _CIRCUIT_SEED, "seed")
    order = _selection_order(selection)
    if simulator_id == "trotterization" and model.c_ops_local:
        raise ValueError("Trotterization is closed-system only")
    groups, reducers = _pauli_expectation_groups(simulator_id, sites, measure_id)
    circuit = import_optional("shadowsim.backends.circuit", extra="qiskit")
    module_name = (
        "shadowsim.simulators.trotterization_simulator"
        if simulator_id == "trotterization"
        else "shadowsim.simulators.splitjmatrix_simulator"
    )
    simulator_module = import_optional(module_name, extra="qiskit")
    simulator_cls = (
        simulator_module.TrotterizationSimulator
        if simulator_id == "trotterization"
        else simulator_module.SplitJMatrixSimulator
    )
    return simulator_cls(
        model.local_hamiltonians,
        model.c_ops_local,
        state,
        num_qubits=model.num_qubits,
        total_time=total_time,
        time_steps=steps,
        num_steps=num_steps,
        trotter_depth=depth,
        shots=shots,
        seed=seed,
        measurement_groups=groups,
        reducers=reducers,
        circuit_backend=circuit.AerCircuitBackend(),
        **({"x_qubits": sites} if measure_id == "x" else {}),
        **({"order": order} if simulator_id == "trotterization" else {}),
    )


def _selection_positive_int(selection: Mapping[str, object], key: str, default: int, name: str) -> int:
    """Return a positive integer from ``selection``, or ``default`` when the key is absent."""
    if key not in selection:
        return default
    number = _named_integer(selection[key], name)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
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


def _choice(selection: Mapping[str, object], key: str) -> str:
    """Return a string id from ``selection``, or an empty string when it is absent."""
    value = selection.get(key)
    if isinstance(value, str):
        return value
    return ""


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


def _model(model_id: str, qubits: object, emitters: object = None) -> IsingModel | TavisCummingsModel:
    """Build the selected factory.

    Ising reads ``qubits``. Jaynes–Cummings is always 3 qubits. Tavis–Cummings
    reads ``emitters`` and uses two cavity qubits plus one qubit per emitter.
    """
    record = next((item for item in listed_models() if item["id"] == model_id), None)
    if record is None:
        raise ValueError("unknown model")
    factory = getattr(models, record["id"])
    if model_id == "tavis_cummings":
        built = factory(n_emitters=_emitter_count(emitters))
    elif record["qubits"]:
        built = factory(n_qubits=_integer(qubits))
    else:
        built = factory()
    return cast(IsingModel | TavisCummingsModel, built)


def _measure_sites(selection: Mapping[str, object], num_qubits: int) -> list[int]:
    """Return qubit indexes to measure. Missing ``sites`` means every qubit."""
    raw = selection.get("sites")
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


def _pauli_expectation_groups(
    simulator_id: str,
    sites: list[int],
    measure_id: str,
) -> tuple[list[list[int]], list[object]]:
    """Return one single-qubit group per selected site, reduced to ``<Z>`` or ``<X>``."""
    offset = 1 if simulator_id == "splitjmatrix" else 0
    groups = [[site + offset] for site in sites]
    reducer = expectation_x if measure_id == "x" else expectation_z
    return groups, [reducer for _ in sites]


def _observables(num_qubits: int, measure_id: str, sites: list[int]) -> list[Operator]:
    """Return one Pauli on each selected qubit for ``measure_id``."""
    if measure_id not in ("x", "z"):
        raise ValueError("unknown measurement")
    letter = measure_id.upper()
    observables: list[Operator] = []
    for site in sites:
        label = ["I"] * num_qubits
        label[site] = letter
        observables.append(Operator("".join(label)))
    return observables


def _state_data(selection: Mapping[str, object], state_id: str) -> object:
    """Return the posted payload for ``state_id``."""
    key = {"basis": "basis", "gray": "gray", "angle": "angles", "amplitude": "amplitudes"}[state_id]
    return selection.get(key)


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
