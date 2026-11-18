"""Research CLI subcommands: model, simulate, compare, and run."""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from shadowsim.backends.catalog import listed_backends
from shadowsim.cli.document import (
    build_run_document,
    load_document,
    model_stub,
    parse_id_list,
)
from shadowsim.cli.run import run_page
from shadowsim.models.catalog import listed_models
from shadowsim.simulators.catalog import listed_simulators

_SUPPRESS = argparse.SUPPRESS


def add_research_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register ``model``, ``simulate``, ``compare``, and ``run``."""
    add_model_parser(subparsers)
    add_simulate_parser(subparsers)
    add_compare_parser(subparsers)
    add_run_parser(subparsers)


def add_model_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ``shadowsim model``."""
    parser = subparsers.add_parser("model", help="Build a model section from factory arguments.")
    parser.add_argument(
        "model",
        choices=_model_ids(),
        help="Model factory id from the catalog.",
    )
    parser.add_argument("--qubits", type=int, help="Qubit count for factories that take n_qubits.")
    _add_model_param_flags(parser)
    _add_format_flags(parser)
    parser.set_defaults(handler=run_model)


def add_simulate_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ``shadowsim simulate``."""
    parser = subparsers.add_parser("simulate", help="Run one simulator from CLI flags.")
    _add_shared_run_flags(parser, backends=False)
    parser.set_defaults(handler=run_simulate)


def add_compare_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ``shadowsim compare``."""
    parser = subparsers.add_parser(
        "compare",
        help="Run one simulator on multiple backends and compare them.",
    )
    _add_shared_run_flags(parser, backends=True)
    parser.set_defaults(handler=run_compare)


def add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ``shadowsim run``."""
    parser = subparsers.add_parser("run", help="Run a version 1 JSON or YAML experiment file.")
    parser.add_argument("path", help="Path to a .json, .yaml, or .yml run document.")
    parser.add_argument(
        "--output-dir",
        help="Directory that save and export paths must stay under.",
    )
    _add_format_flags(parser)
    parser.set_defaults(handler=run_run)


def run_model(args: argparse.Namespace) -> int:
    """Print a model stub built from factory flags."""
    stub = model_stub(
        args.model,
        arguments=_model_arguments(args.model, args),
        qubits=getattr(args, "qubits", None),
    )
    if args.print_document or args.format == "json":
        _emit_json(stub)
        return 0
    model = stub["model"]
    assert isinstance(model, Mapping)
    print(f"model: {model['id']}")
    arguments = model.get("arguments", {})
    assert isinstance(arguments, Mapping)
    if not arguments:
        print("arguments: (defaults)")
        return 0
    print("arguments:")
    for key in sorted(arguments):
        print(f"  {key}: {arguments[key]}")
    return 0


def run_simulate(args: argparse.Namespace) -> int:
    """Build and run a single-simulator document."""
    document = _document_from_run_args(args, backends=None)
    return _execute_document(document, args)


def run_compare(args: argparse.Namespace) -> int:
    """Build and run a multi-backend compare document."""
    backends = parse_id_list(args.backends)
    document = _document_from_run_args(args, backends=backends)
    return _execute_document(document, args)


def run_run(args: argparse.Namespace) -> int:
    """Load a document from disk and run it."""
    document = load_document(args.path)
    if args.print_document:
        _emit_json(document)
        return 0
    return _execute_document(document, args)


def _execute_document(document: Mapping[str, object], args: argparse.Namespace) -> int:
    """Optionally print ``document``, then run it and emit the payload."""
    if getattr(args, "print_document", False):
        _emit_json(document)
        return 0
    output_dir = getattr(args, "output_dir", None)
    output_root = Path(output_dir) if output_dir is not None else None
    payload = run_page(document, output_root=output_root)
    _emit_payload(payload, args.format)
    return 0


def _document_from_run_args(
    args: argparse.Namespace,
    *,
    backends: Sequence[str] | None,
) -> dict[str, object]:
    """Compile simulate/compare flags into a version 1 document."""
    return build_run_document(
        model=args.model,
        simulator=args.simulator,
        model_arguments=_model_arguments(args.model, args),
        qubits=getattr(args, "qubits", None),
        total=args.total,
        state=args.state,
        state_value=_parse_state_value(getattr(args, "state_value", None)),
        simulator_arguments=_simulator_arguments(args.simulator, args),
        backend=None if backends is not None else getattr(args, "backend", None),
        backend_arguments=_backend_arguments(args),
        backends=backends,
        measure=args.measure,
        measure_sites=_parse_sites(getattr(args, "sites", None)),
        measure_expression=getattr(args, "expression", None),
        save_path=getattr(args, "save", None),
        export_path=getattr(args, "export", None),
        action_ids=_action_ids(args),
    )


def _add_shared_run_flags(parser: argparse.ArgumentParser, *, backends: bool) -> None:
    """Add model/simulator/backend/output flags shared by simulate and compare."""
    parser.add_argument("--model", required=True, choices=_model_ids(), help="Model factory id.")
    parser.add_argument("--qubits", type=int, help="Qubit count for factories that take n_qubits.")
    _add_model_param_flags(parser)
    parser.add_argument(
        "--simulator",
        required=True,
        choices=_simulator_ids(),
        help="Simulator id from the catalog.",
    )
    _add_simulator_field_flags(parser)
    if backends:
        parser.add_argument(
            "--backends",
            required=True,
            help="Comma-separated backend ids to compare (at least two).",
        )
    else:
        parser.add_argument("--backend", choices=_backend_ids(), help="Circuit backend id.")
    _add_backend_field_flags(parser)
    parser.add_argument("--total", default="0.5", help="Evolution time (default: 0.5).")
    parser.add_argument(
        "--state",
        default="basis",
        choices=("basis", "gray", "angle", "amplitude"),
        help="Initial state id (default: basis).",
    )
    parser.add_argument(
        "--state-value",
        help="State payload: bit string, or JSON list for angle/amplitude.",
    )
    parser.add_argument(
        "--measure",
        default="model",
        help="Measurement id (default: model for factory models).",
    )
    parser.add_argument("--sites", help="Comma-separated qubit indexes for catalog measurements.")
    parser.add_argument("--expression", help="Counts expression when --measure counts.")
    parser.add_argument("--save", help="Save results under this path.")
    parser.add_argument("--export", help="Export metrics JSON under this path.")
    parser.add_argument(
        "--output-dir",
        help="Directory that save and export paths must stay under.",
    )
    _add_format_flags(parser)


def _add_format_flags(parser: argparse.ArgumentParser) -> None:
    """Add stdout format and document-debug flags."""
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Stdout format (default: text).",
    )
    parser.add_argument(
        "--print-document",
        action="store_true",
        help="Print the version 1 run document as JSON and exit without simulating.",
    )


def _add_model_param_flags(parser: argparse.ArgumentParser) -> None:
    """Add optional flags for every catalog model parameter name."""
    for name, help_text in _model_param_help().items():
        parser.add_argument(_cli_flag(name), dest=name, default=_SUPPRESS, help=help_text)


def _add_simulator_field_flags(parser: argparse.ArgumentParser) -> None:
    """Add optional flags for catalog simulator chip fields."""
    for name in _simulator_field_names():
        parser.add_argument(
            _cli_flag(name),
            dest=name,
            default=_SUPPRESS,
            help=f"Simulator argument {name}.",
        )


def _add_backend_field_flags(parser: argparse.ArgumentParser) -> None:
    """Add optional backend argument flags, including shots."""
    parser.add_argument(
        "--shots",
        type=int,
        default=_SUPPRESS,
        help="Shot budget for sampling backends.",
    )
    for name in _backend_field_names():
        if name == "shots":
            continue
        parser.add_argument(
            _cli_flag(name),
            dest=name,
            default=_SUPPRESS,
            help=f"Backend argument {name}.",
        )


def _model_arguments(model_id: str, args: argparse.Namespace) -> dict[str, object]:
    """Return explicitly set model parameters allowed for ``model_id``."""
    allowed = {param["name"] for param in _model_record(model_id)["params"]}
    collected = _present(args, _model_param_names())
    unknown = sorted(set(collected) - allowed)
    if unknown:
        raise ValueError(f"model {model_id} does not take {unknown[0]}")
    return collected


def _simulator_arguments(simulator_id: str, args: argparse.Namespace) -> dict[str, object]:
    """Return explicitly set simulator fields allowed for ``simulator_id``."""
    record = _simulator_record(simulator_id)
    allowed = {field["name"] for field in record["fields"]}
    collected = _present(args, _simulator_field_names())
    unknown = sorted(set(collected) - allowed)
    if unknown:
        raise ValueError(f"simulator {simulator_id} does not take {unknown[0]}")
    return collected


def _backend_arguments(args: argparse.Namespace) -> dict[str, object]:
    """Return explicitly set backend arguments, including shots."""
    names = list(dict.fromkeys([*_backend_field_names(), "shots"]))
    return _present(args, names)


def _action_ids(args: argparse.Namespace) -> list[str] | None:
    """Infer action ids from --save/--export, or leave empty for stdout-only."""
    save = getattr(args, "save", None)
    export = getattr(args, "export", None)
    if save is None and export is None:
        return []
    return None


def _present(args: argparse.Namespace, names: Sequence[str]) -> dict[str, object]:
    """Return ``{name: value}`` for names set on ``args`` (not suppressed)."""
    return {name: getattr(args, name) for name in names if hasattr(args, name)}


def _parse_state_value(raw: object) -> object | None:
    """Parse a CLI state value; JSON lists are decoded when they look like JSON."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text[:1] in {"[", "{"}:
        return json.loads(text)
    return raw


def _parse_sites(raw: object) -> object | None:
    """Parse ``--sites`` as a comma-separated integer list."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if not text:
        return None
    if text.startswith("["):
        return json.loads(text)
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def _emit_payload(payload: Mapping[str, object], fmt: str) -> None:
    """Write a run_page payload to stdout."""
    if fmt == "json":
        _emit_json(payload)
        return
    print(_format_text(payload))


def _emit_json(payload: Mapping[str, object] | dict[str, object]) -> None:
    """Write JSON to stdout."""
    print(json.dumps(payload, indent=2, default=str))


def _format_text(payload: Mapping[str, object]) -> str:
    """Return a short human-readable summary of a run payload."""
    lines: list[str] = []
    if "algorithm" in payload:
        lines.append(f"algorithm: {payload['algorithm']}")
    labels = payload.get("labels")
    if isinstance(labels, list) and labels:
        lines.append("labels: " + ", ".join(str(item) for item in labels))
    resources = payload.get("resources")
    if isinstance(resources, list):
        for item in resources:
            if not isinstance(item, Mapping):
                continue
            title = item.get("title", "simulator")
            wall = item.get("wall_time_s")
            shots = item.get("shots")
            parts = [f"{title}:"]
            if wall is not None:
                parts.append(f"wall_time_s={wall}")
            if shots is not None:
                parts.append(f"shots={shots}")
            lines.append(" ".join(str(part) for part in parts))
    errors = payload.get("errors")
    if errors is not None:
        lines.append(f"errors: {json.dumps(errors, default=str)}")
    if "saved" in payload:
        lines.append(f"saved: {payload['saved']}")
    if "exported" in payload:
        lines.append(f"exported: {payload['exported']}")
    if "runtime" in payload:
        lines.append(f"runtime: {payload['runtime']}")
    if not lines:
        return json.dumps(payload, indent=2, default=str)
    return "\n".join(lines)


def _cli_flag(name: str) -> str:
    """Return the argparse flag for a catalog parameter name."""
    return "--" + name.replace("_", "-")


def _model_ids() -> list[str]:
    return [item["id"] for item in listed_models()]


def _simulator_ids() -> list[str]:
    try:
        return [item["id"] for item in listed_simulators()]
    except ImportError:
        return []


def _backend_ids() -> list[str]:
    try:
        return [item["id"] for item in listed_backends()]
    except ImportError:
        return []


def _model_param_names() -> list[str]:
    return sorted(_model_param_help())


def _model_param_help() -> dict[str, str]:
    help_text: dict[str, str] = {}
    for model in listed_models():
        for param in model["params"]:
            name = param["name"]
            if name in help_text:
                continue
            detail = f"Model argument {name}"
            if param["kind"] == "choice":
                detail += f" ({', '.join(param.get('choices', []))})"
            help_text[name] = detail + "."
    return help_text


def _simulator_field_names() -> list[str]:
    names: set[str] = set()
    try:
        simulators = listed_simulators()
    except ImportError:
        return []
    for item in simulators:
        for field in item["fields"]:
            names.add(field["name"])
    return sorted(names)


def _backend_field_names() -> list[str]:
    names: set[str] = set()
    try:
        backends = listed_backends()
    except ImportError:
        return []
    for item in backends:
        for field in item["fields"]:
            names.add(field["name"])
    return sorted(names)


def _model_record(model_id: str) -> Mapping[str, Any]:
    for item in listed_models():
        if item["id"] == model_id:
            return item
    raise ValueError(f"unknown model {model_id}")


def _simulator_record(simulator_id: str) -> Mapping[str, Any]:
    for item in listed_simulators():
        if item["id"] == simulator_id:
            return item
    raise ValueError(f"unknown simulator {simulator_id}")


__all__ = [
    "add_research_parsers",
    "run_compare",
    "run_model",
    "run_run",
    "run_simulate",
]
