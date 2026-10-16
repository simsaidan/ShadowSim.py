"""List the model factories for the builder page."""

import inspect
from types import ModuleType
from typing import TypedDict

from shadowsim import models
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator


class ListedModel(TypedDict):
    """Display record for one model factory."""

    id: str
    title: str
    detail: str
    phrase: str
    setup: str
    qubits: bool


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
    page can fill that argument from the Qubits setting.

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
            }
        )
    return listed
