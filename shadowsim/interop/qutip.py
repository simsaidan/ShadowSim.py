"""QuTiP ↔ ShadowSim conversion helpers.

Convert QuTiP ``Qobj`` values to ShadowSim core types and back::

    from shadowsim.interop.qutip import from_qutip, to_qutip

    H = from_qutip(qutip_H)                 # → Hamiltonian
    ops = [from_qutip(c) for c in c_ops]    # → Operator
    psi = from_qutip(psi0)                  # → State (ket)

Density matrices have no first-class ShadowSim type; convert them with
``from_qutip(rho, kind="operator")``. Hermitian observables that should stay
``Operator`` (not ``Hamiltonian``) use the same override.
"""

from typing import Literal

import numpy as np
from qutip import Qobj

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.utils.hermitian import hermitian

Kind = Literal["state", "hamiltonian", "operator"]
_VALID_KINDS = frozenset({"state", "hamiltonian", "operator"})


def from_qutip(
    qobj: Qobj,
    *,
    kind: Kind | None = None,
    num_qubits: int | None = None,
    local_dim: int | None = None,
) -> State | Hamiltonian | Operator:
    """Convert a QuTiP ``Qobj`` to a ShadowSim ``State``, ``Hamiltonian``, or ``Operator``.

    When ``kind`` is omitted, inference is:

    - ket or bra → :class:`~shadowsim.core.state.State`
    - square Hermitian oper → :class:`~shadowsim.core.hamiltonian.Hamiltonian`
    - other square oper → :class:`~shadowsim.core.operator.Operator`

    Args:
        qobj: QuTiP quantum object to convert.
        kind: Optional override: ``"state"``, ``"hamiltonian"``, or ``"operator"``.
            Use ``kind="operator"`` for density matrices (no ``DensityOperator`` type).
        num_qubits: Override inferred site count when building a ``State``.
        local_dim: Override inferred local dimension when building a ``State``.

    Returns:
        The corresponding ShadowSim object.

    Raises:
        TypeError: If ``qobj`` is not a ``Qobj``, or ``kind`` is invalid.
        ValueError: If the object type cannot be converted, or state dims are
            ambiguous / inconsistent.
    """
    if not isinstance(qobj, Qobj):
        raise TypeError(f"qobj must be a qutip.Qobj; got {type(qobj)!r}")
    if kind is not None and kind not in _VALID_KINDS:
        raise TypeError(f"kind must be one of {sorted(_VALID_KINDS)}; got {kind!r}")
    if qobj.issuper:
        raise ValueError("cannot convert QuTiP superoperators; expected ket, bra, or oper")

    resolved = kind if kind is not None else _infer_kind(qobj)

    if resolved == "state":
        return _to_state(qobj, num_qubits=num_qubits, local_dim=local_dim)
    if resolved == "hamiltonian":
        return _to_hamiltonian(qobj)
    return _to_operator(qobj)


def to_qutip(obj: State | Operator | Hamiltonian) -> Qobj:
    """Convert a ShadowSim ``State``, ``Operator``, or ``Hamiltonian`` to a QuTiP ``Qobj``.

    Args:
        obj: ShadowSim object to convert.

    Returns:
        A ket ``Qobj`` for ``State`` (flat dims ``[[dim], [1]]``), or an oper
        ``Qobj`` for operators. Flat state dims match dense Hamiltonians passed
        to QuTiP solvers.

    Raises:
        TypeError: If ``obj`` is not a supported ShadowSim type.
    """
    if isinstance(obj, State):
        # Flat dims match ``Qobj(ndarray)`` / mesolve with dense Hamiltonian matrices.
        dim = obj.get_local_dim() ** obj.get_num_qubits()
        return Qobj(np.asarray(obj.state, dtype=np.complex128), dims=[[dim], [1]])

    if isinstance(obj, Operator):
        matrix = np.asarray(obj.matrix, dtype=np.complex128)
        return Qobj(matrix)

    raise TypeError(f"obj must be a shadowsim State, Operator, or Hamiltonian; got {type(obj)!r}")


def _infer_kind(qobj: Qobj) -> Kind:
    if qobj.isket or qobj.isbra:
        return "state"
    if qobj.isoper:
        data = np.asarray(qobj.full(), dtype=np.complex128)
        if data.ndim == 2 and data.shape[0] == data.shape[1] and hermitian(data):
            return "hamiltonian"
        return "operator"
    raise ValueError(f"unsupported QuTiP Qobj type {qobj.type!r}; expected ket, bra, or oper")


def _to_state(
    qobj: Qobj,
    *,
    num_qubits: int | None,
    local_dim: int | None,
) -> State:
    if qobj.isbra:
        qobj = qobj.dag()
    if not qobj.isket:
        raise ValueError(f"kind='state' requires a ket or bra Qobj; got type {qobj.type!r}")

    vec = np.asarray(qobj.full(), dtype=np.complex128).reshape(-1)
    n, d = _resolve_state_layout(qobj.dims[0], num_qubits=num_qubits, local_dim=local_dim)
    return State(vec, n, d)


def _to_hamiltonian(qobj: Qobj) -> Hamiltonian:
    if not qobj.isoper:
        raise ValueError(f"kind='hamiltonian' requires an oper Qobj; got type {qobj.type!r}")
    matrix = np.asarray(qobj.full(), dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"kind='hamiltonian' requires a square oper; got shape {matrix.shape}")
    return Hamiltonian(matrix)


def _to_operator(qobj: Qobj) -> Operator:
    if not qobj.isoper:
        raise ValueError(f"kind='operator' requires an oper Qobj; got type {qobj.type!r}")
    matrix = np.asarray(qobj.full(), dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"kind='operator' requires a square oper; got shape {matrix.shape}")
    return Operator(matrix)


def _resolve_state_layout(
    factors: list[int],
    *,
    num_qubits: int | None,
    local_dim: int | None,
) -> tuple[int, int]:
    if num_qubits is not None or local_dim is not None:
        if num_qubits is None or local_dim is None:
            raise ValueError("num_qubits and local_dim must be provided together")
        return num_qubits, local_dim

    if not factors:
        raise ValueError("cannot infer State layout from empty QuTiP dims")

    ints = [int(f) for f in factors]
    if len(ints) == 1:
        return 1, ints[0]
    if all(f == ints[0] for f in ints):
        return len(ints), ints[0]
    raise ValueError(f"cannot infer homogeneous local_dim from QuTiP dims {ints}; pass num_qubits and local_dim")
