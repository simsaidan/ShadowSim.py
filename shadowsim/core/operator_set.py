"""Collections of quantum operators."""

from collections.abc import Iterator, Sequence

from shadowsim.core.operator import Operator
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum


class OperatorSet:
    """Represent a set of quantum operators."""

    def __init__(self, operators: Sequence[Operator | str | PauliString | PauliSum]) -> None:
        """Initialize an OperatorSet object which represents a set of quantum operators.

        Parameter operators: Operators, or values coercible via ``Operator``
            (Pauli strings / expressions / PauliSum).
        """
        if not isinstance(operators, list):
            raise TypeError(f"operators must be a list; got {type(operators)!r}")
        coerced: list[Operator] = []
        for op in operators:
            if isinstance(op, Operator):
                coerced.append(op)
            elif isinstance(op, (str, PauliString, PauliSum)):
                coerced.append(Operator(op))
            else:
                raise TypeError(f"all operators must be Operator, str, PauliString, or PauliSum; got {type(op)!r}")
        self.operators = coerced
        self.operator_count = len(coerced)

    def __iter__(self) -> Iterator[Operator]:
        """Return an iterator over the operators in the operator set."""
        return iter(self.operators)

    def __len__(self) -> int:
        """Return the number of operators in the operator set."""
        return len(self.operators)

    def __getitem__(self, index: int) -> Operator:
        """Return the operator at the given index."""
        if not isinstance(index, int):
            raise TypeError(f"index must be an integer; got {type(index)!r}")
        if index < 0 or index >= self.operator_count:
            raise IndexError(f"index must be within the range of the operator set; got {index}")
        return self.operators[index]

    def __str__(self) -> str:
        """Return a string representation of the operator set."""
        return f"OperatorSet(operator_count={self.operator_count})"

    def __repr__(self) -> str:
        """Return a string representation of the operator set."""
        return f"OperatorSet(operators={self.operators!r})"
