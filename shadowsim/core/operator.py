"""General quantum operators."""

import numpy as np

from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum, parse_pauli_expression
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.indefinite import indefinite
from shadowsim.utils.negative_semidefinite import negative_semidefinite
from shadowsim.utils.positive_semidefinite import positive_semidefinite
from shadowsim.utils.unitary import unitary

_OperatorInput = np.ndarray | str | PauliString | PauliSum


def _coerce_pauli_sum(value: str | PauliString | PauliSum) -> PauliSum:
    if isinstance(value, PauliSum):
        return value
    if isinstance(value, PauliString):
        return PauliSum.from_pauli_string(value)
    if isinstance(value, str):
        return parse_pauli_expression(value)
    raise TypeError(f"unsupported operator input type: {type(value)!r}")


class Operator:
    """Represent a quantum operator.

    Construct from a dense matrix, a Pauli label/expression string (e.g. ``XII``
    or ``XXI + XYZ``), a :class:`PauliString`, or a :class:`PauliSum`.

    Label-based inputs store a :class:`PauliSum` and only materialize ``.matrix``
    on first access.
    """

    def __init__(self, matrix: _OperatorInput, name: str | None = None):
        """Initialize an Operator object which represents a quantum operator.

        Parameter matrix: Dense matrix, Pauli expression string, PauliString, or PauliSum.
        Parameter name: Optional name; defaults to the Pauli expression when built from labels.
        """
        assert isinstance(name, str) or name is None, "name must be a string or None"
        self._pauli_sum: PauliSum | None = None
        self._matrix_cache: np.ndarray | None = None
        self._flags_ready = False
        self._is_hermitian = False
        self._is_unitary = False
        self._is_positive_semidefinite = False
        self._is_negative_semidefinite = False
        self._is_indefinite = False

        if isinstance(matrix, np.ndarray):
            self._matrix_cache = matrix
            self.dimension = int(matrix.shape[0])
            self.name = name
            self._set_flags_from_matrix(matrix)
        elif isinstance(matrix, (str, PauliString, PauliSum)):
            pauli_sum = _coerce_pauli_sum(matrix)
            self._pauli_sum = pauli_sum
            self.dimension = 2**pauli_sum.num_qubits
            self.name = str(pauli_sum) if name is None else name
        else:
            raise TypeError(f"matrix must be a numpy array, str, PauliString, or PauliSum; got {type(matrix)!r}")

    def _set_flags_from_matrix(self, matrix: np.ndarray) -> None:
        self._is_hermitian = bool(hermitian(matrix))
        self._is_unitary = bool(unitary(matrix))
        self._is_positive_semidefinite = bool(positive_semidefinite(matrix))
        self._is_negative_semidefinite = bool(negative_semidefinite(matrix))
        self._is_indefinite = bool(indefinite(matrix))
        self._flags_ready = True

    def _ensure_matrix(self) -> np.ndarray:
        if self._matrix_cache is None:
            if self._pauli_sum is None:
                raise RuntimeError("Operator has neither a matrix cache nor a PauliSum")
            self._matrix_cache = self._pauli_sum.to_matrix()
            self._set_flags_from_matrix(self._matrix_cache)
        return self._matrix_cache

    def _ensure_flags(self) -> None:
        if self._flags_ready:
            return
        matrix = self._ensure_matrix()
        if not self._flags_ready:
            self._set_flags_from_matrix(matrix)

    @property
    def matrix(self) -> np.ndarray:
        """Return the dense matrix, materializing from a PauliSum if needed."""
        return self._ensure_matrix()

    @property
    def pauli_sum(self) -> PauliSum | None:
        """Return the stored PauliSum, or ``None`` if built from a dense matrix."""
        return self._pauli_sum

    @property
    def is_hermitian(self):
        """Return whether the operator is Hermitian."""
        if self._flags_ready:
            return self._is_hermitian
        if self._pauli_sum is not None and self._matrix_cache is None:
            return self._pauli_sum.is_hermitian()
        self._ensure_flags()
        return self._is_hermitian

    @property
    def is_unitary(self):
        """Return whether the operator is unitary."""
        self._ensure_flags()
        return self._is_unitary

    @property
    def is_positive_semidefinite(self):
        """Return whether the operator is positive semidefinite."""
        self._ensure_flags()
        return self._is_positive_semidefinite

    @property
    def is_negative_semidefinite(self):
        """Return whether the operator is negative semidefinite."""
        self._ensure_flags()
        return self._is_negative_semidefinite

    @property
    def is_indefinite(self):
        """Return whether the operator is indefinite."""
        self._ensure_flags()
        return self._is_indefinite

    def __str__(self):
        """Return a string representation of the operator."""
        if self._pauli_sum is not None and self._matrix_cache is None:
            return f"Operator(pauli_sum={self._pauli_sum})"
        return f"Operator(matrix={self.matrix})"

    def __repr__(self):
        """Return a string representation of the operator."""
        if self._pauli_sum is not None and self._matrix_cache is None:
            return f"Operator(pauli_sum={self._pauli_sum!r})"
        return f"Operator(matrix={self.matrix})"

    def __eq__(self, other):
        """Return whether the operator is equal to another operator."""
        return np.allclose(self.matrix, other.matrix)

    __hash__ = None  # matrix equality uses allclose; instances are not hashable

    def __ne__(self, other):
        """Return whether the operator is not equal to another operator."""
        return not np.allclose(self.matrix, other.matrix)

    def to_operator_set(self):
        """Return an OperatorSet containing the operator."""
        from shadowsim.core.operator_set import OperatorSet  # noqa: PLC0415

        return OperatorSet([self])

    def to_local_operator(self, sites: list[int], local_dim: int = 2):
        """Return a LocalOperator representing the operator acting on the given sites."""
        from shadowsim.core.local_operator import LocalOperator  # noqa: PLC0415

        return LocalOperator(self.matrix, sites, local_dim)

    def set_name(self, name: str | None):
        """Set the operator name."""
        assert isinstance(name, str) or name is None, "name must be a string or None"
        self.name = name
