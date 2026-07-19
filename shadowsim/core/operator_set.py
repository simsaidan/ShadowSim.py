from shadowsim.core.operator import Operator


class OperatorSet:
    def __init__(self, operators: list[Operator]):
        """Initializes an OperatorSet object which represents a set of quantum operators.

        Parameter operators: The list of operators to initialize the operator set with.
        Precondition: operators is a list of Operator objects.
        """
        assert isinstance(operators, list), "operators must be a list"
        assert all(
            isinstance(op, Operator) for op in operators
        ), "all operators must be Operator objects"
        self.operators = operators
        self.operator_count = len(operators)

    def __iter__(self):
        """Returns an iterator over the operators in the operator set."""
        return iter(self.operators)

    def __len__(self):
        """Returns the number of operators in the operator set."""
        return len(self.operators)

    def __getitem__(self, index: int):
        """Returns the operator at the given index."""
        assert isinstance(index, int), "index must be an integer"
        assert (
            index >= 0 and index < self.operator_count
        ), "index must be within the range of the operator set"
        return self.operators[index]

    def __str__(self):
        """Returns a string representation of the operator set."""
        return f"OperatorSet(operator_count={self.operator_count})"

    def __repr__(self):
        """Returns a string representation of the operator set."""
        return f"OperatorSet(operators={self.operators!r})"
