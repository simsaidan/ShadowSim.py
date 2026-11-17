"""List the builder page's initial states, measurements, and result actions.

The page renders a lane from :func:`listed_states`, :func:`listed_measurements`,
or :func:`listed_actions`. :func:`listed_measurements` is the generic list an
added Hamiltonian posts: ``z``, ``x``, ``y``, and ``counts``. A preexisting
model posts ``model`` and records the measurements that factory defines. A
posted catalog id is prepared by the matching function in this module. An id
that is not listed is an error from that function.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, cast

from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.encoding.amplitude import AmplitudeEncoding
from shadowsim.encoding.angle import AngleEncoding
from shadowsim.encoding.computational_basis import ComputationalBasisEncoding
from shadowsim.encoding.gray import GrayEncoding
from shadowsim.encoding.state_encoder import StateEncoder
from shadowsim.simulators.reducers import Measurement

# Basis, Gray, angle, and a posted factory share the page qubit cap. Amplitude
# lists are typed only up to ``_PAGE_AMPLITUDE_CAP``; a longer posted list is
# still prepared.
_PAGE_QUBIT_CAP = 15
_PAGE_AMPLITUDE_CAP = 16


class ListedBitsField(TypedDict):
    """A bit-string chip for one initial state.

    ``cap`` is how many characters the page will type, and how long a posted
    string may be. ``display`` is ``ket`` to show the bits, or ``gray`` to show
    the Gray-decoded ket. ``encode`` is the class the script preview imports.
    ``empty`` is the alert when the string is blank. ``mismatch`` and ``size``
    use ``{n}`` for the qubit count the model fixed. ``blank`` is the detail
    before any bits are typed, and may use ``{cap}``.
    """

    kind: Literal["bits"]
    label: str
    aria: str
    cap: int
    encode: str
    display: Literal["ket", "gray"]
    empty: str
    mismatch: str
    size: str
    blank: str


class ListedNumbersField(TypedDict):
    """A number-list chip for one initial state.

    ``match`` is ``length`` when the list must have one entry per qubit, or
    ``padded`` when the encoding zero-pads to a power of two. ``nonzero`` asks
    the page to reject an all-zero list. ``unit`` is the singular noun in a
    filled detail, such as ``angle``. ``cap`` is the page typing limit and is
    not enforced on a posted list. The other text fields match
    :class:`ListedBitsField`.
    """

    kind: Literal["numbers"]
    label: str
    aria: str
    cap: int
    encode: str
    match: Literal["length", "padded"]
    nonzero: bool
    unit: str
    empty: str
    mismatch: str
    size: str
    blank: str


class ListedState(TypedDict):
    """Display record for one initial state."""

    id: str
    title: str
    detail: str
    phrase: str
    field: ListedBitsField | ListedNumbersField


class ListedExpressionField(TypedDict):
    """The expression chip on a counts measurement."""

    kind: Literal["expression"]
    label: str
    aria: str


class ListedMeasurement(TypedDict):
    """Display record for one measurement.

    ``kind`` is ``pauli`` or ``counts``. A Pauli record has ``letter`` and
    ``rotate``. ``rotate`` is true when a circuit simulator reads those qubits
    in this record's letter, ``X`` or ``Y``, and every other qubit in Z. A
    counts record has ``field`` instead.
    """

    id: str
    title: str
    detail: str
    phrase: str
    kind: Literal["pauli", "counts"]
    letter: NotRequired[str]
    rotate: NotRequired[bool]
    field: NotRequired[ListedExpressionField]


class ListedPathField(TypedDict):
    """A path chip on a result action.

    ``key`` is the posted actions object key. ``default`` fills the chip and is
    the path used when that key is missing.
    """

    kind: Literal["path"]
    key: str
    default: str
    label: str
    aria: str


class ListedAction(TypedDict):
    """Display record for one result action.

    ``plot`` has no ``field``. The page draws it, and preparing a run accepts
    the id without writing a file.
    """

    id: str
    title: str
    detail: str
    phrase: str
    field: NotRequired[ListedPathField]


@dataclass(frozen=True)
class _StateEntry:
    """One initial state, including the encoder ``prepare_state`` calls."""

    id: str
    title: str
    detail: str
    phrase: str
    kind: Literal["bits", "numbers"]
    label: str
    aria: str
    cap: int
    encode: str
    empty: str
    mismatch: str
    size: str
    blank: str
    sized_encoder: Callable[[int], StateEncoder] | None = None
    plain_encoder: Callable[[], StateEncoder] | None = None
    display: Literal["ket", "gray"] | None = None
    match: Literal["length", "padded"] | None = None
    nonzero: bool = False
    unit: str = ""
    bits_label: str = ""
    length_label: str = ""
    value_label: str = ""
    prepared_name: str = ""

    def listed(self) -> ListedState:
        """Return the JSON record for this state."""
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "phrase": self.phrase,
            "field": self._field(),
        }

    def _field(self) -> ListedBitsField | ListedNumbersField:
        """Return the chip description for this state."""
        if self.kind == "bits":
            return {
                "kind": "bits",
                "label": self.label,
                "aria": self.aria,
                "cap": self.cap,
                "encode": self.encode,
                "display": cast(Literal["ket", "gray"], self.display),
                "empty": self.empty,
                "mismatch": self.mismatch,
                "size": self.size,
                "blank": self.blank,
            }
        return {
            "kind": "numbers",
            "label": self.label,
            "aria": self.aria,
            "cap": self.cap,
            "encode": self.encode,
            "match": cast(Literal["length", "padded"], self.match),
            "nonzero": self.nonzero,
            "unit": self.unit,
            "empty": self.empty,
            "mismatch": self.mismatch,
            "size": self.size,
            "blank": self.blank,
        }


@dataclass(frozen=True)
class _MeasurementEntry:
    """One measurement, including how its curves are built."""

    id: str
    title: str
    detail: str
    phrase: str
    kind: Literal["pauli", "counts"]
    letter: str = ""
    rotate: bool = False

    def listed(self) -> ListedMeasurement:
        """Return the JSON record for this measurement."""
        listed: ListedMeasurement = {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "phrase": self.phrase,
            "kind": self.kind,
        }
        if self.kind == "pauli":
            listed["letter"] = self.letter
            listed["rotate"] = self.rotate
            return listed
        listed["field"] = {"kind": "expression", "label": "Expression", "aria": "Counts expression"}
        return listed


@dataclass(frozen=True)
class _ActionEntry:
    """One result action. A path action fills ``path_key``."""

    id: str
    title: str
    detail: str
    phrase: str
    path_key: str = ""
    path_default: str = ""
    path_label: str = ""
    path_aria: str = ""

    def listed(self) -> ListedAction:
        """Return the JSON record for this action."""
        listed: ListedAction = {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "phrase": self.phrase,
        }
        if self.path_key:
            listed["field"] = {
                "kind": "path",
                "key": self.path_key,
                "default": self.path_default,
                "label": self.path_label,
                "aria": self.path_aria,
            }
        return listed


_BIT_MISMATCH = "Must be {n} bits."
_BIT_BLANK = "0s and 1s, up to {cap}"

_STATES: tuple[_StateEntry, ...] = (
    _StateEntry(
        "basis",
        "Basis state",
        "Bit string of 0 and 1",
        "Basis state",
        "bits",
        "Bits",
        "Basis bits",
        _PAGE_QUBIT_CAP,
        "ComputationalBasisEncoding",
        "Enter a bit string",
        _BIT_MISMATCH,
        "Enter a {n}-bit basis string",
        _BIT_BLANK,
        sized_encoder=ComputationalBasisEncoding,
        display="ket",
        bits_label="basis bits",
        length_label="basis bit string",
    ),
    _StateEntry(
        "gray",
        "Gray code",
        "Gray-coded bit string",
        "Gray code",
        "bits",
        "Bits",
        "Gray bits",
        _PAGE_QUBIT_CAP,
        "GrayEncoding",
        "Enter a bit string",
        _BIT_MISMATCH,
        "Enter a {n}-bit Gray code string",
        _BIT_BLANK,
        sized_encoder=GrayEncoding,
        display="gray",
        bits_label="Gray code bits",
        length_label="Gray code bit string",
    ),
    _StateEntry(
        "angle",
        "Angle",
        "Rotation angles per qubit",
        "Angle",
        "numbers",
        "Radians",
        "Angles",
        _PAGE_QUBIT_CAP,
        "AngleEncoding",
        "Enter one angle per qubit",
        "Must be {n} angles.",
        "Enter {n} angles",
        "Radians, one per qubit",
        plain_encoder=AngleEncoding,
        match="length",
        unit="angle",
        value_label="angles",
    ),
    _StateEntry(
        "amplitude",
        "Amplitude",
        "Custom amplitudes, auto-padded",
        "Amplitude",
        "numbers",
        "Amplitudes",
        "Amplitudes",
        _PAGE_AMPLITUDE_CAP,
        "AmplitudeEncoding",
        "Enter a non-zero amplitude list",
        "Must prepare {n} qubits.",
        "Enter amplitudes for {n} qubits",
        "Up to {cap} numbers",
        plain_encoder=AmplitudeEncoding,
        match="padded",
        nonzero=True,
        unit="qubit",
        value_label="amplitudes",
        prepared_name="amplitude encoding",
    ),
)

_MEASUREMENTS: tuple[_MeasurementEntry, ...] = (
    _MeasurementEntry("z", "Z expectation", "On each qubit", "Z expectation on each qubit", "pauli", "Z", False),
    _MeasurementEntry("x", "X expectation", "On each qubit", "X expectation on each qubit", "pauli", "X", True),
    _MeasurementEntry("y", "Y expectation", "On each qubit", "Y expectation on each qubit", "pauli", "Y", True),
    _MeasurementEntry("counts", "Counts", "Expression on all qubits", "Counts on all qubits", "counts"),
)

_ACTIONS: tuple[_ActionEntry, ...] = (
    _ActionEntry("plot", "Plot results", "Curves for each observable", "plot results"),
    _ActionEntry(
        "save",
        "Save results",
        "Write arrays and metadata to disk",
        "save results",
        "save_path",
        "results/run1",
        "Path",
        "Save path",
    ),
    _ActionEntry(
        "export",
        "Export metrics",
        "Runtime and shot budget as JSON",
        "export metrics",
        "export_path",
        "results",
        "Path",
        "Export path",
    ),
)

_STATE_BY_ID = {entry.id: entry for entry in _STATES}
_MEASUREMENT_BY_ID = {entry.id: entry for entry in _MEASUREMENTS}
_ACTION_BY_ID = {entry.id: entry for entry in _ACTIONS}


def listed_states() -> list[ListedState]:
    """Return the initial states in catalog order.

    ``field.cap`` is the page typing limit. Basis and Gray preparation also
    reject a longer bit string. Angle and amplitude preparation do not reject a
    list longer than ``cap``.

    Returns:
        States the builder page can offer.
    """
    return [entry.listed() for entry in _STATES]


def listed_measurements() -> list[ListedMeasurement]:
    """Return the generic measurements in catalog order.

    The ids are ``z``, ``x``, ``y``, and ``counts``. ``GET /measurements``
    returns this list, and an added Hamiltonian posts one of these ids. A
    preexisting model posts ``model`` and records the measurements that
    factory defines.

    Returns:
        Measurements the builder page offers for an added Hamiltonian.
    """
    return [entry.listed() for entry in _MEASUREMENTS]


def listed_actions() -> list[ListedAction]:
    """Return the result actions in catalog order.

    Returns:
        Actions the builder page can offer.
    """
    return [entry.listed() for entry in _ACTIONS]


def measurement_record(measure_id: str) -> ListedMeasurement:
    """Return the measurement named ``measure_id``.

    Args:
        measure_id: An id from :func:`listed_measurements`.

    Returns:
        The display record, including ``kind`` and any chip field.

    Raises:
        ValueError: ``measure_id`` is not listed.
    """
    return _measurement(measure_id).listed()


def action_record(action_id: str) -> ListedAction:
    """Return the result action named ``action_id``.

    Args:
        action_id: An id from :func:`listed_actions`.

    Returns:
        The display record. A path action includes its default.

    Raises:
        ValueError: ``action_id`` is not listed.
    """
    entry = _ACTION_BY_ID.get(action_id)
    if entry is None:
        raise ValueError("unknown action")
    return entry.listed()


def prepare_state(state_id: str, num_qubits: int, data: object = None) -> State:
    """Prepare ``state_id`` on ``num_qubits`` qubits from the posted ``data``.

    A bit-string state must be that many characters of 0 and 1, and no longer
    than its ``cap``. ``angle`` is one finite real per qubit. ``amplitude`` is a
    non-empty list of finite reals, and the padded state must use ``num_qubits``.

    Args:
        state_id: An id from :func:`listed_states`.
        num_qubits: Qubits the model has.
        data: The posted ``state.value``.

    Returns:
        The encoded initial state.

    Raises:
        ValueError: ``state_id`` is not listed, or ``data`` does not fit it.
    """
    entry = _STATE_BY_ID.get(state_id)
    if entry is None:
        raise ValueError("unknown initial state")
    if entry.kind == "bits":
        return _prepare_bits(entry, num_qubits, data)
    return _prepare_numbers(entry, num_qubits, data)


def measurements_for(measure: Mapping[str, object], num_qubits: int) -> list[Measurement]:
    """Return one expectation per selected qubit, or one counts expression.

    Missing ``sites`` measures every qubit. A Pauli measurement reads each
    selected qubit in the basis it was measured in.

    Args:
        measure: Posted measurement with ``id``, optional ``sites``, and
            ``expression`` for counts.
        num_qubits: Qubits the model has.

    Returns:
        Measurements in ``sites`` order.

    Raises:
        ValueError: The id is not listed, ``sites`` is not a list of indexes, or
            a counts measurement has no expression.
    """
    entry = _measurement(_measure_id(measure))
    sites = _sites(measure, num_qubits)
    if entry.kind == "pauli":
        return [Measurement((site,), '(counts["0"] - counts["1"]) / shots', f"expectation on {site}") for site in sites]
    expression = measure.get("expression")
    if not isinstance(expression, str):
        raise ValueError("a counts measurement needs an expression")
    return [Measurement(tuple(sites), expression)]


def labels_for(measure: Mapping[str, object], num_qubits: int) -> list[str]:
    """Return one chart name per curve.

    A Pauli measurement on qubits 0 and 1 is ``⟨Z⟩ on 0`` and ``⟨Z⟩ on 1``,
    using that record's letter. Counts uses its expression.

    Args:
        measure: Posted measurement, as in :func:`measurements_for`.
        num_qubits: Qubits the model has.

    Returns:
        Chart names in ``sites`` order.

    Raises:
        ValueError: The id is not listed, or the measurement cannot be built.
    """
    entry = _measurement(_measure_id(measure))
    if entry.kind == "counts":
        return [item.label for item in measurements_for(measure, num_qubits)]
    return [f"⟨{entry.letter}⟩ on {site}" for site in _sites(measure, num_qubits)]


def observables_for(num_qubits: int, measure_id: str, sites: list[int]) -> list[Operator]:
    """Return one Pauli on each selected qubit.

    Args:
        num_qubits: Qubits the operator acts on.
        measure_id: A Pauli id from :func:`listed_measurements`.
        sites: Qubit indexes, in the order the operators are returned.

    Returns:
        One operator per site, with that measurement's letter on the site and
        ``I`` elsewhere.

    Raises:
        ValueError: ``measure_id`` is not listed, or it is not a Pauli measurement.
    """
    entry = _measurement(measure_id)
    if entry.kind != "pauli":
        raise ValueError("a counts measurement has no Pauli operators")
    observables: list[Operator] = []
    for site in sites:
        label = ["I"] * num_qubits
        label[site] = entry.letter
        observables.append(Operator("".join(label)))
    return observables


def _measurement(measure_id: str) -> _MeasurementEntry:
    """Return the measurement entry named ``measure_id``.

    Raises:
        ValueError: ``measure_id`` is not listed.
    """
    entry = _MEASUREMENT_BY_ID.get(measure_id)
    if entry is None:
        raise ValueError("unknown measurement")
    return entry


def _measure_id(measure: Mapping[str, object]) -> str:
    """Return ``measure["id"]`` when it is a string, otherwise an empty string."""
    value = measure.get("id")
    if isinstance(value, str):
        return value
    return ""


def _prepare_bits(entry: _StateEntry, num_qubits: int, data: object) -> State:
    """Encode a bit string whose length is ``num_qubits``."""
    bits = _bit_string(data, entry.bits_label, entry.cap)
    if len(bits) != num_qubits:
        raise ValueError(f"{entry.length_label} length must equal the qubit count ({num_qubits})")
    encoder = cast(Callable[[int], StateEncoder], entry.sized_encoder)
    return encoder(num_qubits).encode(bits)


def _prepare_numbers(entry: _StateEntry, num_qubits: int, data: object) -> State:
    """Encode a real list, and require a padded encoding to match ``num_qubits``."""
    count = num_qubits if entry.match == "length" else None
    values = _real_list(data, count, entry.value_label)
    encoder = cast(Callable[[], StateEncoder], entry.plain_encoder)
    state = encoder().encode(values)
    if entry.match == "padded":
        _prepared_count(state, num_qubits, entry.prepared_name)
    return state


def _prepared_count(state: State, num_qubits: int, name: str) -> None:
    """Raise when ``state`` was not prepared on ``num_qubits`` qubits.

    Raises:
        ValueError: The encoded state has a different qubit count.
    """
    prepared = state.get_num_qubits()
    if prepared == num_qubits:
        return
    prepared_label = "qubit" if prepared == 1 else "qubits"
    model_label = "qubit" if num_qubits == 1 else "qubits"
    raise ValueError(f"{name} prepares {prepared} {prepared_label}, model has {num_qubits} {model_label}")


def _bit_string(value: object, label: str, cap: int) -> list[int]:
    """Return ``value`` as bits when it is a string of 0 and 1, at most ``cap`` characters.

    Raises:
        ValueError: ``value`` is not that string.
    """
    if not isinstance(value, str) or not value or len(value) > cap or any(bit not in "01" for bit in value):
        raise ValueError(f"{label} must be a string of 0 and 1, at most {cap} characters")
    return [int(bit) for bit in value]


def _real_list(value: object, count: int | None, label: str) -> list[float]:
    """Return ``value`` as finite real numbers, and require ``count`` of them when set.

    Raises:
        ValueError: ``value`` is not that list.
    """
    expected = f"{count} finite real numbers" if count is not None else "a non-empty list of finite real numbers"
    if not isinstance(value, list) or not value or (count is not None and len(value) != count):
        raise ValueError(f"{label} must be {expected}")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise ValueError(f"{label} must be {expected}")
        numbers.append(float(item))
    return numbers


def _sites(measure: Mapping[str, object], num_qubits: int) -> list[int]:
    """Return qubit indexes to measure. Missing ``sites`` means every qubit.

    Raises:
        ValueError: ``sites`` is present and is not a non-empty list of indexes
            in ``0 .. num_qubits - 1``.
    """
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
