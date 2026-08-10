"""Collections of quantum operators."""

from shadowsim.core.operator import Operator
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum


class OperatorSet:
    """Represent a set of quantum operators."""

    def __init__(self, operators: list):
        """Initialize an OperatorSet object which represents a set of quantum operators.

        Parameter operators: Operators, or values coercible via :class:`Operator`
            (Pauli strings / expressions / PauliSum).
        """
        assert isinstance(operators, list), "operators must be a list"
        coerced: list[Operator] = []
        for op in operators:
            if isinstance(op, Operator):
                coerced.append(op)
            elif isinstance(op, (str, PauliString, PauliSum)):
                coerced.append(Operator(op))
            else:
                assert False, "all operators must be Operator objects"
        self.operators = coerced
        self.operator_count = len(coerced)

    def __iter__(self):
        """Return an iterator over the operators in the operator set."""
        return iter(self.operators)

    def __len__(self):
        """Return the number of operators in the operator set."""
        return len(self.operators)

    def __getitem__(self, index: int):
        """Return the operator at the given index."""
        assert isinstance(index, int), "index must be an integer"
        assert index >= 0 and index < self.operator_count, "index must be within the range of the operator set"
        return self.operators[index]

    def __str__(self):
        """Return a string representation of the operator set."""
        return f"OperatorSet(operator_count={self.operator_count})"

    def __repr__(self):
        """Return a string representation of the operator set."""
        return f"OperatorSet(operators={self.operators!r})"
