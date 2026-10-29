"""List the model factories for the builder page."""

import inspect
import types
from collections.abc import Sequence
from types import ModuleType
from typing import Literal, NotRequired, TypedDict, Union, get_args, get_origin

from shadowsim import models
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator

# The page fills these itself, or they are not free parameters.
# ``n_qubits`` comes from the Qubits setting. Emitter count, cavity count, and
# hopping already have their own chip fields. ``cavity_levels`` is fixed at 4,
# and ``initial_fock`` only builds the factory state the page replaces.
_SKIPPED_PARAMS = frozenset(
    {
        "n_qubits",
        "n_emitters",
        "n_cavities",
        "nu",
        "cavity_levels",
        "initial_fock",
    }
)

# ``custom`` is the topology ``ising`` reports after ``edges`` is set. Passing
# it as ``topology`` is not a preset the factory accepts on its own.
_HIDDEN_CHOICES: dict[str, frozenset[str]] = {"topology": frozenset({"custom"})}


class ListedParam(TypedDict):
    """One factory argument the builder page can edit.

    ``choices`` is present when ``kind`` is ``choice``. ``default`` is the text
    that fills the chip. An empty ``edges`` default means the chain preset.
    """

    name: str
    label: str
    kind: Literal["number", "choice", "edges", "number_or_list"]
    default: str
    choices: NotRequired[list[str]]


class ListedModel(TypedDict):
    """Display record for one model factory."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str
    qubits: bool
    params: list[ListedParam]


class ListedModelTerm(ListedModel):
    """A Hamiltonian or Lindblad block that can be added beside a model factory."""

    adds: bool
    symbol: str
    stem: str


_TERMS: tuple[tuple[str, str, str, type], ...] = (
    ("hamiltonian", "Add a Hamiltonian", "added_hamiltonian", Hamiltonian),
    ("local_hamiltonian", "Add a Local Hamiltonian", "added_local_hamiltonian", LocalHamiltonian),
    ("lindblad", "Add a Lindblad operator", "lindblad", Operator),
)


def listed_models() -> list[ListedModel]:
    """Return the public model factories in ``__all__`` order.

    Classes are omitted. A factory that requires ``n_qubits`` is marked so the
    page can fill that argument from the Qubits setting. ``params`` lists the
    other factory arguments the chip can edit, with defaults filled in.

    Returns:
        Models the builder page can offer.
    """
    return _describe_models(models)


def listed_model_terms() -> list[ListedModelTerm]:
    """Return Hamiltonian and Lindblad blocks in a fixed order.

    Each record names the class the block constructs. ``adds`` tells the page to
    keep the chosen model factory when the block is placed.

    Returns:
        Operator blocks the builder page can add to a model.
    """
    listed: list[ListedModelTerm] = []
    for term_id, title, stem, cls in _TERMS:
        document = inspect.getdoc(cls)
        detail = title if not document else document.split("\n", 1)[0].replace("``", "")
        required = [
            parameter.name
            for parameter in inspect.signature(cls).parameters.values()
            if parameter.default is inspect.Parameter.empty
        ]
        listed.append(
            {
                "id": term_id,
                "title": title,
                "detail": detail,
                "phrase": title,
                "setup": f"{{name}} = {cls.__name__}({', '.join(required)})",
                "qubits": False,
                "params": [],
                "adds": True,
                "symbol": cls.__name__,
                "stem": stem,
            }
        )
    return listed


def _describe_models(module: ModuleType) -> list[ListedModel]:
    """Describe factory functions exported by ``module``."""
    listed: list[ListedModel] = []
    for name in getattr(module, "__all__", ()):
        value = getattr(module, name, None)
        if not inspect.isfunction(value) or not value.__module__.startswith("shadowsim.models"):
            continue
        title = "-".join(part.capitalize() for part in name.split("_"))
        document = inspect.getdoc(value)
        detail = title if document is None else document.split("\n", 1)[0].replace("``", "")
        required = [
            parameter.name
            for parameter in inspect.signature(value).parameters.values()
            if parameter.default is inspect.Parameter.empty
        ]
        arguments = ["n_qubits={qubits}" if parameter == "n_qubits" else parameter for parameter in required]
        listed.append(
            {
                "id": name,
                "title": title,
                "detail": detail,
                "phrase": title,
                "setup": f"model = {name}({', '.join(arguments)})",
                "qubits": "n_qubits" in required,
                "params": _listed_params(value),
            }
        )
    return listed


def _listed_params(factory: types.FunctionType) -> list[ListedParam]:
    """Return editable factory arguments in signature order.

    Parameters in :data:`_SKIPPED_PARAMS` are omitted, as are arguments that
    have no default. A float default is formatted so ``float`` reads it back.
    """
    listed: list[ListedParam] = []
    for parameter in inspect.signature(factory).parameters.values():
        if parameter.name in _SKIPPED_PARAMS or parameter.default is inspect.Parameter.empty:
            continue
        listed.append(_listed_param(parameter))
    return listed


def _listed_param(parameter: inspect.Parameter) -> ListedParam:
    """Describe one editable parameter."""
    if parameter.name == "edges":
        return {
            "name": parameter.name,
            "label": parameter.name,
            "kind": "edges",
            "default": "" if parameter.default is None else _default_text(parameter.default),
        }
    choices = _literal_choices(parameter.annotation)
    if choices is not None:
        hidden = _HIDDEN_CHOICES.get(parameter.name, frozenset())
        return {
            "name": parameter.name,
            "label": parameter.name,
            "kind": "choice",
            "default": _default_text(parameter.default),
            "choices": [choice for choice in choices if choice not in hidden],
        }
    kind: Literal["number", "number_or_list"] = (
        "number_or_list" if _accepts_sequence(parameter.annotation) else "number"
    )
    return {
        "name": parameter.name,
        "label": parameter.name,
        "kind": kind,
        "default": _default_text(parameter.default),
    }


def _literal_choices(annotation: object) -> list[str] | None:
    """Return string members of a ``Literal`` annotation."""
    if get_origin(annotation) is not Literal:
        return None
    return [item for item in get_args(annotation) if isinstance(item, str)]


def _accepts_sequence(annotation: object) -> bool:
    """Return whether ``annotation`` is a float or a sequence of floats."""
    origin = get_origin(annotation)
    if origin not in (Union, types.UnionType):
        return False
    args = get_args(annotation)
    has_float = any(arg is float for arg in args)
    has_sequence = any(arg is Sequence or get_origin(arg) is Sequence for arg in args)
    return has_float and has_sequence


def _default_text(value: object) -> str:
    """Return chip text for a factory default.

    Sixteen significant digits round-trips the cavity Lindblad amplitudes.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    if isinstance(value, float):
        return format(value, ".16g")
    return str(value)
