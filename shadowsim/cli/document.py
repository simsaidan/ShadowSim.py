"""Build and load version 1 run documents for the research CLI."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from shadowsim._optional import import_optional
from shadowsim.backends.catalog import listed_backends
from shadowsim.cli.catalog import listed_actions, listed_measurements, listed_states
from shadowsim.models.catalog import listed_models
from shadowsim.simulators.catalog import listed_simulators

_RUN_VERSION = 1


def parse_id_list(text: str) -> list[str]:
    """Split a comma-separated id list, stripping blanks.

    Raises:
        ValueError: ``text`` has no ids after splitting.
    """
    ids = [part.strip() for part in text.split(",") if part.strip()]
    if not ids:
        raise ValueError("expected a comma-separated list of ids")
    return ids


def model_section(
    model_id: str,
    *,
    arguments: Mapping[str, object] | None = None,
    qubits: int | str | None = None,
) -> dict[str, object]:
    """Return the ``model`` section for a factory ``model_id``.

    ``qubits`` is written as ``n_qubits`` when the catalog marks the factory as
    taking that argument. Explicit ``arguments`` win over ``qubits`` when both
    set ``n_qubits``.

    Raises:
        ValueError: ``model_id`` is not a listed factory.
    """
    record = _model_record(model_id)
    bound: dict[str, object] = dict(arguments or {})
    if qubits is not None and record["qubits"] and "n_qubits" not in bound:
        bound["n_qubits"] = qubits
    return {"id": model_id, "arguments": bound}


def simulator_entry(
    simulator_id: str,
    *,
    arguments: Mapping[str, object] | None = None,
    backend_id: str | None = None,
    backend_arguments: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return one ``simulators`` entry.

    Raises:
        ValueError: ``simulator_id`` or ``backend_id`` is not listed.
    """
    _simulator_record(simulator_id)
    if backend_id is None:
        backend: object = None
    else:
        _backend_record(backend_id)
        backend = {"id": backend_id, "arguments": dict(backend_arguments or {})}
    return {
        "id": simulator_id,
        "arguments": dict(arguments or {}),
        "backend": backend,
    }


def expand_compare_backends(
    simulator_id: str,
    backends: Sequence[str],
    *,
    simulator_arguments: Mapping[str, object] | None = None,
    backend_arguments: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Expand one simulator and many backends into ``simulators`` entries.

    The first backend is the benchmark reference. Shared ``backend_arguments``
    are copied onto every entry.

    Raises:
        ValueError: Fewer than two backends, a duplicate id, or an unknown id.
    """
    ids = [item.strip() for item in backends if str(item).strip()]
    if len(ids) < 2:
        raise ValueError("compare needs at least two backends")
    if len(set(ids)) != len(ids):
        raise ValueError("compare backends must be unique")
    return [
        simulator_entry(
            simulator_id,
            arguments=simulator_arguments,
            backend_id=backend_id,
            backend_arguments=backend_arguments,
        )
        for backend_id in ids
    ]


def actions_section(
    *,
    action_ids: Sequence[str] | None = None,
    save_path: str | None = None,
    export_path: str | None = None,
) -> dict[str, object]:
    """Return the ``actions`` section.

    When ``action_ids`` is omitted, ``save`` and/or ``export`` are included for
    any path that was passed. An empty id list is allowed for stdout-only runs.

    Raises:
        ValueError: An action id is not listed.
    """
    if action_ids is None:
        ids: list[str] = []
        if save_path is not None:
            ids.append("save")
        if export_path is not None:
            ids.append("export")
    else:
        ids = list(action_ids)
    known = {item["id"] for item in listed_actions()}
    for action_id in ids:
        if action_id not in known:
            raise ValueError(f"unknown action {action_id}")
    actions: dict[str, object] = {"ids": ids}
    if save_path is not None:
        actions["save_path"] = save_path
    if export_path is not None:
        actions["export_path"] = export_path
    return actions


def build_document(
    *,
    model: Mapping[str, object],
    simulators: Sequence[Mapping[str, object]],
    total: object = "0.5",
    state_id: str = "basis",
    state_value: object | None = None,
    measure_id: str = "model",
    measure_sites: object | None = None,
    measure_expression: object | None = None,
    actions: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Assemble a version 1 run document.

    Missing ``state_value`` defaults to an all-zero bit string when ``state_id``
    is ``basis`` or ``gray`` and the model arguments include ``n_qubits``.

    Raises:
        ValueError: A listed id is unknown, ``simulators`` is empty, or the
            model section is not a factory object.
    """
    if not simulators:
        raise ValueError("simulators must be a non-empty list")
    _state_record(state_id)
    if measure_id != "model":
        _measurement_record(measure_id)
    resolved_value = state_value
    if resolved_value is None:
        resolved_value = _default_state_value(state_id, _n_qubits(model))
    measure: dict[str, object] = {"id": measure_id, "sites": measure_sites}
    if measure_expression is not None:
        measure["expression"] = measure_expression
    return {
        "version": _RUN_VERSION,
        "total": total,
        "state": {"id": state_id, "value": resolved_value},
        "model": dict(model),
        "simulators": [dict(entry) for entry in simulators],
        "measure": measure,
        "actions": dict(actions) if actions is not None else actions_section(),
    }


def build_run_document(
    *,
    model: str,
    simulator: str,
    model_arguments: Mapping[str, object] | None = None,
    qubits: int | str | None = None,
    total: object = "0.5",
    state: str = "basis",
    state_value: object | None = None,
    simulator_arguments: Mapping[str, object] | None = None,
    backend: str | None = None,
    backend_arguments: Mapping[str, object] | None = None,
    backends: Sequence[str] | None = None,
    measure: str = "model",
    measure_sites: object | None = None,
    measure_expression: object | None = None,
    save_path: str | None = None,
    export_path: str | None = None,
    action_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    """Build a version 1 document from research-CLI fields.

    Pass ``backend`` for a single run, or ``backends`` (at least two) for a
    compare document. Passing both is an error.

    Raises:
        ValueError: Both ``backend`` and ``backends`` are set, compare has
            fewer than two backends, or a catalog id is unknown.
    """
    if backend is not None and backends is not None:
        raise ValueError("pass backend or backends, not both")
    model_body = model_section(model, arguments=model_arguments, qubits=qubits)
    if backends is not None:
        entries = expand_compare_backends(
            simulator,
            backends,
            simulator_arguments=simulator_arguments,
            backend_arguments=backend_arguments,
        )
    else:
        entries = [
            simulator_entry(
                simulator,
                arguments=simulator_arguments,
                backend_id=backend,
                backend_arguments=backend_arguments,
            )
        ]
    return build_document(
        model=model_body,
        simulators=entries,
        total=total,
        state_id=state,
        state_value=state_value,
        measure_id=measure,
        measure_sites=measure_sites,
        measure_expression=measure_expression,
        actions=actions_section(
            action_ids=action_ids,
            save_path=save_path,
            export_path=export_path,
        ),
    )


def model_stub(
    model_id: str,
    *,
    arguments: Mapping[str, object] | None = None,
    qubits: int | str | None = None,
) -> dict[str, object]:
    """Return a document stub that only fills the model section.

    The stub keeps empty ``simulators`` out of the validated run shape so
    callers can print construction output without choosing a simulator.
    """
    return {
        "version": _RUN_VERSION,
        "model": model_section(model_id, arguments=arguments, qubits=qubits),
    }


def load_document(path: str | Path) -> dict[str, object]:
    """Load a version 1 run document from JSON or YAML.

    ``.json`` is always supported. ``.yaml`` / ``.yml`` need the ``yaml`` extra.

    Raises:
        ValueError: The suffix is unsupported, or the file is not a JSON/YAML
            object.
        OSError: The file cannot be read.
        ImportError: A YAML file was given without the ``yaml`` extra.
        json.JSONDecodeError: The JSON text is invalid.
    """
    location = Path(path)
    suffix = location.suffix.lower()
    text = location.read_text(encoding="utf-8")
    if suffix == ".json":
        payload = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        payload = _load_yaml(text)
    else:
        raise ValueError(f"unsupported document type {suffix or location.name}")
    if not isinstance(payload, dict):
        raise ValueError("run document must be an object")
    return payload


def _load_yaml(text: str) -> Any:
    """Parse YAML text, or explain how to install the extra."""
    yaml = import_optional("yaml", extra="yaml")
    return yaml.safe_load(text)


def _model_record(model_id: str) -> Mapping[str, object]:
    for item in listed_models():
        if item["id"] == model_id:
            return item
    raise ValueError(f"unknown model {model_id}")


def _simulator_record(simulator_id: str) -> Mapping[str, object]:
    try:
        listed = listed_simulators()
    except ImportError:
        listed = []
    for item in listed:
        if item["id"] == simulator_id:
            return item
    raise ValueError(f"unknown simulator {simulator_id}")


def _backend_record(backend_id: str) -> Mapping[str, object]:
    try:
        listed = listed_backends()
    except ImportError:
        listed = []
    for item in listed:
        if item["id"] == backend_id:
            return item
    raise ValueError(f"unknown backend {backend_id}")


def _state_record(state_id: str) -> Mapping[str, object]:
    for item in listed_states():
        if item["id"] == state_id:
            return item
    raise ValueError(f"unknown initial state {state_id}")


def _measurement_record(measure_id: str) -> Mapping[str, object]:
    for item in listed_measurements():
        if item["id"] == measure_id:
            return item
    raise ValueError(f"unknown measurement {measure_id}")


def _n_qubits(model: Mapping[str, object]) -> int | None:
    arguments = model.get("arguments")
    if not isinstance(arguments, Mapping):
        return None
    raw = arguments.get("n_qubits")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _default_state_value(state_id: str, num_qubits: int | None) -> object | None:
    if num_qubits is None or num_qubits < 1:
        return None
    if state_id in {"basis", "gray"}:
        return "0" * num_qubits
    return None
