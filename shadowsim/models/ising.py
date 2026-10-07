"""Classical and transverse-field Ising model factory."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum
from shadowsim.core.state import State
from shadowsim.simulators.reducers import population_one
from shadowsim.utils.tensor import tensor

Reducer = Callable[[dict[str, int]], float]

FieldKind = Literal["classical", "transverse"]
TopologyKind = Literal["chain", "custom"]
BoundaryKind = Literal["open", "periodic"]

_DEFAULT_TOPOLOGY: TopologyKind = "chain"
_DEFAULT_BOUNDARY: BoundaryKind = "open"


@dataclass(frozen=True)
class IsingModel:
    """Bundled operators for a classical or transverse-field Ising Hamiltonian.

    Qubits are labeled ``0 .. num_qubits - 1``. Couplings act on the edge set
    ``edges``; single-site fields are on every qubit. Contiguous nearest-neighbor
    ZZ terms (``|i - j| == 1``) and single-site fields are exposed as
    :class:`~shadowsim.core.local_hamiltonian.LocalHamiltonian` terms for
    Split-J / Trotter. Non-contiguous ZZ edges (periodic wrap or custom
    long-range couplings) appear only in ``full_hamiltonians`` / ``pauli_sum``.

    Attributes:
        full_hamiltonians: Hamiltonian terms in the full Hilbert space.
        local_hamiltonians: Contiguous local Hamiltonian terms.
        c_ops_full: Lindblad operators in the full space (empty; closed system).
        c_ops_local: Local Lindblad operators (empty; closed system).
        psi0: Default initial state (all-|0⟩ classical, all-|+⟩ transverse).
        e_ops: Per-site ``Z`` observables.
        measurement_groups: One Split-J group per qubit site.
        reducers: Split-J count reducers matching ``measurement_groups``.
        pauli_sum: Full Hamiltonian as a sparse Pauli sum.
        edges: Resolved undirected interaction pairs ``(i, j)`` with ``i < j``.
        num_qubits: Number of qubits.
        J: Coupling strength.
        h: Field strength.
        field: ``"classical"`` (Z field) or ``"transverse"`` (X field).
        topology: ``"chain"`` or ``"custom"`` when ``edges`` was supplied.
        boundary: Boundary condition used for chain presets (``"open"`` for custom).
    """

    full_hamiltonians: list[Hamiltonian]
    local_hamiltonians: list[LocalHamiltonian]
    c_ops_full: list[Operator]
    c_ops_local: list[LocalOperator]
    psi0: State
    e_ops: list[Operator]
    measurement_groups: list[int | list[int]]
    reducers: Sequence[Reducer]
    pauli_sum: PauliSum
    edges: list[tuple[int, int]]
    num_qubits: int
    J: float
    h: float
    field: FieldKind
    topology: TopologyKind
    boundary: BoundaryKind

    @property
    def hamiltonian(self) -> Hamiltonian:
        """Return the combined full-space Hamiltonian."""
        return Hamiltonian(self.pauli_sum)


def _chain_edges(n_qubits: int, boundary: BoundaryKind) -> list[tuple[int, int]]:
    """Return nearest-neighbor edges for a 1D chain."""
    edges = [(i, i + 1) for i in range(n_qubits - 1)]
    if boundary == "periodic":
        edges.append((0, n_qubits - 1))
    return edges


def _normalize_edges(n_qubits: int, edges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Validate and normalize an undirected edge list."""
    normalized: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        if not isinstance(edge, tuple) or len(edge) != 2:
            raise ValueError(f"each edge must be a pair (i, j), got {edge!r}")
        i, j = int(edge[0]), int(edge[1])
        if i == j:
            raise ValueError(f"self-loop edges are not allowed, got ({i}, {j})")
        if not (0 <= i < n_qubits and 0 <= j < n_qubits):
            raise ValueError(f"edge ({i}, {j}) is out of range for n_qubits={n_qubits}")
        pair = (min(i, j), max(i, j))
        if pair in seen:
            raise ValueError(f"duplicate edge {pair}")
        seen.add(pair)
        normalized.append(pair)
    return normalized


def _pauli_label(n_qubits: int, support: dict[int, str]) -> str:
    """Build a Pauli word with leftmost = qubit 0."""
    chars = ["I"] * n_qubits
    for site, label in support.items():
        chars[site] = label
    return "".join(chars)


def _resolve_edges(
    *,
    n_qubits: int,
    topology: TopologyKind,
    boundary: BoundaryKind,
    edges: Sequence[tuple[int, int]] | None,
) -> tuple[list[tuple[int, int]], TopologyKind, BoundaryKind]:
    """Resolve preset or custom connectivity."""
    if edges is not None:
        if topology != _DEFAULT_TOPOLOGY or boundary != _DEFAULT_BOUNDARY:
            raise ValueError(
                "edges cannot be combined with a non-default topology or boundary; "
                f"got topology={topology!r}, boundary={boundary!r}"
            )
        return _normalize_edges(n_qubits, edges), "custom", "open"

    if topology != "chain":
        raise ValueError(f"unsupported topology {topology!r}; expected 'chain' or pass edges=")
    if boundary not in ("open", "periodic"):
        raise ValueError(f"unsupported boundary {boundary!r}; expected 'open' or 'periodic'")
    if boundary == "periodic" and n_qubits < 3:
        raise ValueError(f"periodic boundary requires n_qubits >= 3, got {n_qubits}")
    return _chain_edges(n_qubits, boundary), "chain", boundary


def ising(
    *,
    n_qubits: int,
    J: float = 1.0,
    h: float = 0.0,
    field: FieldKind = "transverse",
    topology: TopologyKind = _DEFAULT_TOPOLOGY,
    boundary: BoundaryKind = _DEFAULT_BOUNDARY,
    edges: Sequence[tuple[int, int]] | None = None,
) -> IsingModel:
    """Build a classical or transverse-field Ising model.

    Classical field::

        H = J ∑_{(i,j)∈E} Z_i Z_j + h ∑_i Z_i

    Transverse field::

        H = J ∑_{(i,j)∈E} Z_i Z_j + h ∑_i X_i

    Connectivity ``E`` comes from a 1D chain preset (``topology="chain"`` with
    ``boundary="open"`` or ``"periodic"``) or from an explicit ``edges`` list.

    Args:
        n_qubits: Number of qubits (at least 2).
        J: ZZ coupling strength.
        h: On-site field strength.
        field: ``"classical"`` for a Z field, ``"transverse"`` for an X field.
        topology: Preset graph when ``edges`` is omitted (only ``"chain"``).
        boundary: Chain boundary condition when ``edges`` is omitted.
        edges: Optional undirected interaction pairs. When set, overrides
            topology/boundary (which must remain at their defaults).

    Returns:
        An ``IsingModel`` with full/local Hamiltonians and default closed-system
        simulation helpers.

    Raises:
        ValueError: On invalid size, field, topology, boundary, edges, or when
            both ``J`` and ``h`` are zero (no Hamiltonian terms).
    """
    if not isinstance(n_qubits, int) or n_qubits < 2:
        raise ValueError(f"n_qubits must be an integer >= 2, got {n_qubits}")
    if field not in ("classical", "transverse"):
        raise ValueError(f"field must be 'classical' or 'transverse', got {field!r}")

    j_coup = float(J)
    h_field = float(h)
    if j_coup == 0.0 and h_field == 0.0:
        raise ValueError("J and h cannot both be zero")

    resolved_edges, resolved_topology, resolved_boundary = _resolve_edges(
        n_qubits=n_qubits,
        topology=topology,
        boundary=boundary,
        edges=edges,
    )

    field_pauli = "Z" if field == "classical" else "X"
    terms: dict[str, complex] = {}
    if j_coup != 0.0:
        for i, j in resolved_edges:
            label = _pauli_label(n_qubits, {i: "Z", j: "Z"})
            terms[label] = terms.get(label, 0.0) + j_coup
    if h_field != 0.0:
        for site in range(n_qubits):
            label = _pauli_label(n_qubits, {site: field_pauli})
            terms[label] = terms.get(label, 0.0) + h_field

    if not terms:
        raise ValueError("Ising Hamiltonian has no terms; provide edges with J != 0 or h != 0")

    pauli_sum = PauliSum(terms)

    local_hamiltonians: list[LocalHamiltonian] = []
    full_hamiltonians: list[Hamiltonian] = []

    zz_local = PauliString.from_string("ZZ").matrix()
    field_local = PauliString.from_string(field_pauli).matrix()

    if j_coup != 0.0:
        for i, j in resolved_edges:
            label = _pauli_label(n_qubits, {i: "Z", j: "Z"})
            full_hamiltonians.append(Hamiltonian(PauliSum({label: j_coup})))
            if j - i == 1:
                local_hamiltonians.append(LocalHamiltonian(j_coup * zz_local, [i, j]))

    if h_field != 0.0:
        for site in range(n_qubits):
            label = _pauli_label(n_qubits, {site: field_pauli})
            full_hamiltonians.append(Hamiltonian(PauliSum({label: h_field})))
            local_hamiltonians.append(LocalHamiltonian(h_field * field_local, [site]))

    if field == "classical":
        psi0_vec = np.zeros(2**n_qubits, dtype=np.complex128)
        psi0_vec[0] = 1.0
    else:
        plus = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2.0)
        psi0_vec = tensor([plus] * n_qubits)

    psi0 = State(psi0_vec, n_qubits)
    e_ops = [Operator(_pauli_label(n_qubits, {site: "Z"})) for site in range(n_qubits)]
    measurement_groups: list[int | list[int]] = list(range(n_qubits))
    reducers: tuple[Reducer, ...] = tuple(population_one for _ in range(n_qubits))

    return IsingModel(
        full_hamiltonians=full_hamiltonians,
        local_hamiltonians=local_hamiltonians,
        c_ops_full=[],
        c_ops_local=[],
        psi0=psi0,
        e_ops=e_ops,
        measurement_groups=measurement_groups,
        reducers=reducers,
        pauli_sum=pauli_sum,
        edges=resolved_edges,
        num_qubits=n_qubits,
        J=j_coup,
        h=h_field,
        field=field,
        topology=resolved_topology,
        boundary=resolved_boundary,
    )
