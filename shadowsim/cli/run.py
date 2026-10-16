"""Build a QuTiP simulator from a builder-page selection."""

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from shadowsim import models
from shadowsim._optional import import_optional
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.encoding.amplitude import AmplitudeEncoding
from shadowsim.encoding.angle import AngleEncoding
from shadowsim.encoding.computational_basis import ComputationalBasisEncoding
from shadowsim.encoding.gray import GrayEncoding
from shadowsim.models.catalog import listed_models
from shadowsim.models.ising import IsingModel
from shadowsim.models.tavis_cummings import TavisCummingsModel

if TYPE_CHECKING:
    from shadowsim.simulators.qutip_simulator import QutipSimulator

_STATES = frozenset({"basis", "gray", "angle", "amplitude"})


def build_simulator(selection: Mapping[str, object], *, time_steps: int = 101) -> "QutipSimulator":
    """Build a QuTiP simulator for one builder-page selection.

    Args:
        selection: Page ids and settings. ``then`` is ignored. ``backend`` must
            be ``aer``. ``measure`` must be ``x`` or ``z``.
            ``model`` is a factory name from :func:`shadowsim.models.catalog.listed_models`.
            Factories that require ``n_qubits`` read ``qubits``. The others ignore it.
            A basis state reads ``basis``, a string of 0 and 1 whose length is the
            qubit count, at most 15 characters.
        time_steps: Points on the solver grid. Defaults to the page preview.

    Returns:
        A simulator that has not been run.

    Raises:
        ValueError: The selection cannot run in this slice.
        ImportError: The QuTiP extra is not installed.
    """
    if isinstance(time_steps, bool) or not isinstance(time_steps, int) or time_steps < 1:
        raise ValueError("time_steps must be a positive integer")
    if _choice(selection, "simulator") != "qutip":
        raise ValueError("only QuTiP can run from the page")
    backend = _choice(selection, "backend")
    if backend == "qiskit":
        raise ValueError("a caller-supplied Qiskit backend cannot run from the page")
    if backend != "aer":
        raise ValueError("only Aer can run from the page")
    state_id = _choice(selection, "state")
    if state_id not in _STATES:
        raise ValueError("unknown initial state")
    total_time = _positive_number(selection.get("total"))
    model = _model(_choice(selection, "model"), selection.get("qubits"))
    state = _initial_state(state_id, model.num_qubits, selection.get("basis"))
    observables = _observables(model.num_qubits, _choice(selection, "measure"))
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


def _model(model_id: str, qubits: object) -> IsingModel | TavisCummingsModel:
    """Build the selected factory. Factories without ``n_qubits`` ignore ``qubits``."""
    record = next((item for item in listed_models() if item["id"] == model_id), None)
    if record is None:
        raise ValueError("unknown model")
    factory = getattr(models, record["id"])
    if record["qubits"]:
        built = factory(n_qubits=_integer(qubits))
    else:
        built = factory()
    return cast(IsingModel | TavisCummingsModel, built)


def _observables(num_qubits: int, measure_id: str) -> list[Operator]:
    """Return one Pauli per qubit for ``measure_id``."""
    if measure_id not in ("x", "z"):
        raise ValueError("unknown measurement")
    letter = measure_id.upper()
    observables: list[Operator] = []
    for site in range(num_qubits):
        label = ["I"] * num_qubits
        label[site] = letter
        observables.append(Operator("".join(label)))
    return observables


def _basis_bits(value: object) -> list[int]:
    """Return ``value`` as bits when it is a string of 0 and 1, at most 15 characters."""
    if not isinstance(value, str) or not value or len(value) > 15 or any(bit not in "01" for bit in value):
        raise ValueError("basis bits must be a string of 0 and 1, at most 15 characters")
    return [int(bit) for bit in value]


def _initial_state(state_id: str, num_qubits: int, basis: object = None) -> State:
    """Prepare ``state_id`` on ``num_qubits`` qubits."""
    if state_id == "basis":
        bits = _basis_bits(basis)
        if len(bits) != num_qubits:
            raise ValueError(f"basis bit string length must equal the qubit count ({num_qubits})")
        return ComputationalBasisEncoding(num_qubits).encode(bits)
    if state_id == "gray":
        bits = [1, *([0] * (num_qubits - 1))]
        return GrayEncoding(num_qubits).encode(bits)
    if state_id == "angle":
        angles = [0.0] * num_qubits
        angles[0] = math.pi / 2
        if num_qubits > 1:
            angles[1] = math.pi / 4
        return AngleEncoding().encode(angles)
    if state_id != "amplitude":
        raise ValueError("unknown initial state")
    amplitudes = [0.0] * (2**num_qubits)
    for index, value in enumerate((1.0, 0.5, 0.25)):
        if index < len(amplitudes):
            amplitudes[index] = value
    return AmplitudeEncoding().encode(amplitudes)
