"""Turn measurement counts into numbers.

A :class:`Measurement` reads chosen qubits from a counts dict and evaluates one
arithmetic expression on them. :func:`apply_measurements` does that for every
time point of a :class:`~shadowsim.simulators.result.SimulationResult`.
"""

import ast
import math
import operator
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import cast

import numpy as np

from shadowsim.simulators.result import SimulationResult

QUBIT_EXPECTATIONS = "qubit_expectations"
"""``observable_kind`` metadata of a result with one Pauli expectation per qubit."""

_MAX_EXPRESSION_LENGTH = 1000
_POPULATION = 'counts["1"] / shots'
_EXPECTATION = '(counts["0"] - counts["1"]) / shots'
_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _parse(expression: str, width: int) -> ast.expr:
    """Return the checked syntax tree of ``expression`` for ``width`` measured qubits.

    Raises:
        ValueError: ``expression`` is not text, is too long, does not parse, or
            uses anything other than numbers, ``shots``, ``counts["..."]``,
            parentheses, unary ``+`` / ``-``, and ``+ - * / **``.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("expression must be non-empty text")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError(f"expression must be at most {_MAX_EXPRESSION_LENGTH} characters")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"expression is not valid: {exc.msg}") from None
    _check(tree.body, width)
    return tree.body


def _check(node: ast.expr, width: int) -> None:
    """Reject any node the expression language does not allow."""
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        _check(node.left, width)
        _check(node.right, width)
        return
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        _check(node.operand, width)
        return
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return
    if isinstance(node, ast.Name) and node.id == "shots":
        return
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "counts":
        key = node.slice
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise ValueError('counts must be read with a quoted bitstring, such as counts["01"]')
        if len(key.value) != width or any(bit not in "01" for bit in key.value):
            raise ValueError(f'counts keys must be {width} characters of 0 and 1, got "{key.value}"')
        return
    raise ValueError(f"expression cannot use {ast.unparse(node)!r}")


def _value(node: ast.expr, counts: dict[str, int], shots: int) -> float:
    """Evaluate a tree that :func:`_check` accepted."""
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](_value(node.left, counts, shots), _value(node.right, counts, shots))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_value(node.operand, counts, shots))
    if isinstance(node, ast.Constant):
        return float(cast(float, node.value))
    if isinstance(node, ast.Name):
        return float(shots)
    key = cast(ast.Constant, cast(ast.Subscript, node).slice)
    return float(counts.get(cast(str, key.value), 0))


@dataclass(frozen=True)
class Measurement:
    """One number per time point, computed from the shot counts of chosen qubits.

    ``expression`` may use numbers, parentheses, unary ``+`` and ``-``,
    ``+ - * / **``, ``shots``, and ``counts["01"]``. A ``counts`` key has one
    character per entry of ``qubits``, in that order, so with ``qubits=(2, 0)``
    ``counts["10"]`` is the number of shots where qubit 2 read 1 and qubit 0 read 0.
    A bitstring that was never observed is 0. ``shots`` is the total number of
    shots at that time point. Values are floats, so ``**`` cannot build an
    unbounded integer.

    The counts must come from a run in the basis this expression assumes. A
    Measurement does not change or check that basis.

    Attributes:
        qubits: System qubit indexes, in the order a ``counts`` key lists them.
        expression: Arithmetic on ``counts`` and ``shots``.
        label: Name of the resulting curve. Defaults to ``expression``.

    Examples:
        Probability that qubits 0 and 1 agree:

        ```python exec="1" source="above" result="text"
        from shadowsim.simulators import Measurement

        same = Measurement((0, 1), '(counts["00"] + counts["11"]) / shots')
        print(same.evaluate({"000": 6, "110": 2, "011": 2}))
        ```
    """

    qubits: tuple[int, ...]
    expression: str
    label: str = ""
    _tree: ast.expr = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Check ``qubits`` and parse ``expression``.

        Raises:
            ValueError: ``qubits`` is empty, repeats an index, or holds something
                other than non-negative integers, or ``expression`` is not allowed.
        """
        if isinstance(self.qubits, (str, bytes)) or not isinstance(self.qubits, Sequence):
            raise ValueError("qubits must be a non-empty list of qubit indexes")
        qubits = tuple(self.qubits)
        if not qubits:
            raise ValueError("qubits must be a non-empty list of qubit indexes")
        for qubit in qubits:
            if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0:
                raise ValueError("qubits must be non-negative integer indexes")
        if len(set(qubits)) != len(qubits):
            raise ValueError("qubits must not repeat an index")
        object.__setattr__(self, "qubits", qubits)
        object.__setattr__(self, "_tree", _parse(self.expression, len(qubits)))
        if not self.label:
            object.__setattr__(self, "label", self.expression.strip())

    @classmethod
    def population(cls, qubit: int) -> "Measurement":
        """Return the fraction of shots where ``qubit`` read 1."""
        return cls((qubit,), _POPULATION, f"P(1) on {qubit}")

    @classmethod
    def expectation(cls, qubit: int) -> "Measurement":
        """Return the Pauli expectation of ``qubit`` in the basis it was measured in.

        A read of 0 counts as ``+1`` and a read of 1 as ``-1``.
        """
        return cls((qubit,), _EXPECTATION, f"expectation on {qubit}")

    @classmethod
    def cavity_population(cls, first: int, second: int) -> "Measurement":
        """Return the mean photon number of a cavity stored on two qubits.

        Uses the notebook convention ``(3*N("11") + 2*N("10") + N("01")) / shots``,
        where the first bit of each key is ``first``.
        """
        return cls(
            (first, second),
            '(3 * counts["11"] + 2 * counts["10"] + counts["01"]) / shots',
            f"cavity population on {first}, {second}",
        )

    def evaluate(self, counts: dict[str, int]) -> float:
        """Return this measurement on one time point's counts.

        Args:
            counts: Bitstring to shot count, where bit ``i`` of a key is system qubit ``i``.

        Raises:
            ValueError: A key is too short for ``qubits``, the expression divides
                by zero or overflows, or the result is not a finite real number.
        """
        last = max(self.qubits)
        marginal: dict[str, int] = {}
        for bitstring, shot_count in counts.items():
            if len(bitstring) <= last:
                raise ValueError(f"counts have {len(bitstring)} qubits, but this measurement reads qubit {last}")
            key = "".join(bitstring[qubit] for qubit in self.qubits)
            marginal[key] = marginal.get(key, 0) + shot_count
        try:
            value: object = _value(self._tree, marginal, sum(counts.values()))
        except ZeroDivisionError:
            raise ValueError(f"{self.label} divides by zero") from None
        except OverflowError:
            raise ValueError(f"{self.label} is too large") from None
        if not isinstance(value, float) or not math.isfinite(value):
            raise ValueError(f"{self.label} must be a finite real number")
        return value


def apply_measurements(result: SimulationResult, measurements: Sequence[Measurement]) -> SimulationResult:
    """Return ``result`` with one curve per measurement in place of its observables.

    Each curve has one value per entry of ``result.counts``. The metadata gains
    ``measurements``: the qubits, expression, and label of each one, in order.

    Only a sampling backend, such as Aer, records counts. An expectation backend,
    such as PauliPropagation, returns one Pauli expectation per qubit instead
    (``observable_kind`` is ``"qubit_expectations"``). Its result can only be read
    with :meth:`Measurement.expectation` and :meth:`Measurement.population`.

    Raises:
        ValueError: ``measurements`` is empty, or a measurement cannot be
            evaluated on ``result``.
    """
    if not measurements:
        raise ValueError("at least one measurement is required")
    if result.counts is None:
        curves = [_from_expectations(result, item) for item in measurements]
    else:
        curves = [
            np.array([item.evaluate(counts) for counts in result.counts], dtype=np.float64) for item in measurements
        ]
    recorded = [
        {"qubits": list(item.qubits), "expression": item.expression, "label": item.label} for item in measurements
    ]
    metadata = {key: value for key, value in result.metadata.items() if key != "observable_kind"}
    return replace(result, observables=curves, metadata={**metadata, "measurements": recorded})


def _from_expectations(result: SimulationResult, item: Measurement) -> np.ndarray:
    """Return ``item`` read from a result with one Pauli expectation per qubit."""
    backend = result.metadata.get("circuit_backend")
    source = f"the {backend} backend" if backend else "this result"
    if result.metadata.get("observable_kind") != QUBIT_EXPECTATIONS:
        raise ValueError(
            f"{source} has no shot counts, so a counts measurement cannot run on it; "
            "use a sampling backend such as Aer, or read Pauli expectations instead"
        )
    if len(item.qubits) != 1 or item.expression not in (_EXPECTATION, _POPULATION):
        raise ValueError(
            f"{source} returns Pauli expectations, not shot counts, so it can only read "
            f"Measurement.expectation and Measurement.population; {item.label} needs a sampling backend such as Aer"
        )
    qubit = item.qubits[0]
    if qubit >= len(result.observables):
        raise ValueError(f"the result has {len(result.observables)} qubits, but this measurement reads qubit {qubit}")
    expectation = np.asarray(result.observables[qubit], dtype=np.float64)
    if item.expression == _POPULATION:
        return (1.0 - expectation) / 2.0
    return expectation.copy()
