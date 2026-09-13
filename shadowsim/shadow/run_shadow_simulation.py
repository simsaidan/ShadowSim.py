"""Helpers and result type for running shadow dynamics."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator
from shadowsim.core.operator_set import OperatorSet
from shadowsim.core.state import State
from shadowsim.shadow.shadow_hamiltonian import ShadowHamiltonian, _infer_num_qubits
from shadowsim.shadow.shadow_state import ShadowState
from shadowsim.simulators.qutip_simulator import QutipSimulator
from shadowsim.utils.next_power_of_two import next_power_of_two


@dataclass(frozen=True)
class ShadowSimulationResult:
    """Outputs from a shadow-space dynamics run.

    Attributes:
        times: Simulation time grid.
        expectations: One expectation trajectory per shadow-space observable.
        labels: Names for each trajectory in ``expectations``.
        shadow_hamiltonian: Constructed shadow Hamiltonian (includes unpadded ``H_S``).
        shadow_state: Shadow state aligned to the closure basis order.
        H_S_padded: ``H_S`` embedded in the top-left of a ``2**shadow_num_qubits`` matrix.
        shadow_num_qubits: Qubit count of the padded shadow Hilbert space.
    """

    times: np.ndarray
    expectations: list[np.ndarray]
    labels: list[str]
    shadow_hamiltonian: ShadowHamiltonian
    shadow_state: ShadowState
    H_S_padded: np.ndarray
    shadow_num_qubits: int


def computational_basis_projectors(num_qubits: int) -> OperatorSet:
    """Return computational-basis projectors on a ``num_qubits``-qubit space.

    For ``n`` qubits this yields ``2**n`` rank-1 projectors ``|k⟩⟨k|`` labeled
    ``P_{bits}`` (e.g. ``P_00``, ``P_01``, …).
    """
    if num_qubits < 0:
        raise ValueError(f"num_qubits must be non-negative, got {num_qubits}")
    dim = 1 << num_qubits
    ops: list[Operator] = []
    for i in range(dim):
        bits = format(i, f"0{num_qubits}b") if num_qubits > 0 else ""
        p = np.zeros((dim, dim), dtype=np.complex128)
        p[i, i] = 1.0
        ops.append(Operator(p, name=f"P_{bits}" if num_qubits > 0 else "P_"))
    return OperatorSet(ops)


def pad_h_s(H_S: np.ndarray) -> tuple[np.ndarray, int]:
    """Embed ``H_S`` in the top-left of the next power-of-two square matrix.

    Returns:
        ``(H_S_padded, shadow_num_qubits)`` where ``H_S_padded`` has shape
        ``(D, D)`` with ``D = next_power_of_two(m)`` for an ``m×m`` input, and
        ``shadow_num_qubits = log2(D)`` (``0`` when ``D == 1``).
    """
    matrix = np.asarray(H_S, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"H_S must be a square matrix, got shape {matrix.shape}")
    m = int(matrix.shape[0])
    d = next_power_of_two(m)
    if d == m:
        padded = matrix.copy()
    else:
        padded = np.zeros((d, d), dtype=np.complex128)
        padded[:m, :m] = matrix
    shadow_num_qubits = d.bit_length() - 1
    return padded, shadow_num_qubits


def _as_hamiltonian_list(hamiltonians: Hamiltonian | Sequence[Hamiltonian]) -> list[Hamiltonian]:
    if isinstance(hamiltonians, Hamiltonian):
        return [hamiltonians]
    terms = list(hamiltonians)
    if not terms:
        raise ValueError("shadow simulation: hamiltonians must be a non-empty sequence")
    return terms


def _as_operator_set(observables: OperatorSet | Sequence[Operator | str]) -> OperatorSet:
    if isinstance(observables, OperatorSet):
        ops = observables
    else:
        ops = OperatorSet(list(observables))
    if len(ops) == 0:
        raise ValueError("shadow simulation: observables must be non-empty")
    return ops


def _validate_physical_dims(
    terms: list[Hamiltonian],
    observables: OperatorSet,
    initial_state: State,
    num_qubits: int,
) -> None:
    expected_dim = 2**num_qubits
    state_nq = initial_state.get_num_qubits()
    if state_nq != num_qubits:
        raise ValueError(
            "shadow simulation: initial_state qubit count disagrees with num_qubits; "
            f"got state num_qubits={state_nq}, expected {num_qubits}"
        )
    if initial_state.state.shape[0] != expected_dim:
        raise ValueError(
            "shadow simulation: initial_state dimension disagrees with num_qubits; "
            f"got length {initial_state.state.shape[0]}, expected {expected_dim}"
        )
    for h in terms:
        if isinstance(h, LocalHamiltonian):
            continue
        if int(h.dimension) != expected_dim:
            raise ValueError(
                "shadow simulation: Hamiltonian dimension disagrees with num_qubits; "
                f"got dimension {h.dimension}, expected {expected_dim}"
            )
    for op in observables.operators:
        if int(op.dimension) != expected_dim:
            raise ValueError(
                "shadow simulation: observable dimension disagrees with num_qubits; "
                f"got dimension {op.dimension}, expected {expected_dim}"
            )


def run_shadow_simulation(
    hamiltonians: Hamiltonian | Sequence[Hamiltonian],
    observables: OperatorSet | Sequence[Operator | str],
    initial_state: State,
    *,
    total_time: float,
    time_steps: int,
    num_qubits: int | None = None,
    shadow_observables: OperatorSet | None = None,
    tol: float = 1e-10,
    verbose: bool = False,
) -> ShadowSimulationResult:
    """Build the shadow model and evolve it with :class:`QutipSimulator`.

    Constructs :class:`ShadowHamiltonian` on the physical system, builds a
    :class:`ShadowState` ordered to match the closure basis of ``H_S``, pads
    ``H_S`` to a power-of-two Hilbert space, and simulates with QuTiP.
    Default shadow-space observables are computational-basis projectors.

    Example:
        ```python
        import numpy as np
        from shadowsim.core import Hamiltonian, OperatorSet, State
        from shadowsim.shadow import run_shadow_simulation

        result = run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            total_time=1.0,
            time_steps=11,
        )
        print(result.shadow_num_qubits, result.shadow_hamiltonian.basis)
        ```
    """
    terms = _as_hamiltonian_list(hamiltonians)
    operator_set = _as_operator_set(observables)
    nq = num_qubits if num_qubits is not None else _infer_num_qubits(terms)
    if nq < 0:
        raise ValueError(f"shadow simulation: num_qubits must be non-negative, got {nq}")
    _validate_physical_dims(terms, operator_set, initial_state, nq)

    shadow_h = ShadowHamiltonian(
        operator_set,
        terms,
        num_qubits=nq,
        tol=tol,
        verbose=verbose,
    )
    H_S_padded, shadow_nq = pad_h_s(shadow_h.H_S)
    closure_ops = OperatorSet(list(shadow_h.basis))
    shadow_state = ShadowState(initial_state, closure_ops, num_qubits=shadow_nq)

    if shadow_state.get_num_qubits() != shadow_nq:
        raise ValueError(
            "shadow simulation: padded shadow state qubit count disagrees with padded H_S; "
            f"got state num_qubits={shadow_state.get_num_qubits()}, expected {shadow_nq}"
        )
    if shadow_state.state.shape[0] != H_S_padded.shape[0]:
        raise ValueError(
            "shadow simulation: padded shadow state dimension disagrees with padded H_S; "
            f"got state length {shadow_state.state.shape[0]}, H_S shape {H_S_padded.shape}"
        )

    e_ops = shadow_observables if shadow_observables is not None else computational_basis_projectors(shadow_nq)
    if len(e_ops) == 0:
        raise ValueError("shadow simulation: shadow_observables must be non-empty")
    expected_shadow_dim = 1 << shadow_nq
    for op in e_ops.operators:
        if int(op.dimension) != expected_shadow_dim:
            raise ValueError(
                "shadow simulation: shadow_observables dimension disagrees with shadow space; "
                f"got dimension {op.dimension}, expected {expected_shadow_dim}"
            )

    simulator = QutipSimulator(
        [Hamiltonian(H_S_padded)],
        [],
        shadow_state,
        e_ops,
        shadow_nq,
        total_time,
        time_steps,
    )
    simulator.simulate()
    expectations = list(simulator.get_results())
    labels = [op.name if op.name is not None else str(i) for i, op in enumerate(e_ops)]

    return ShadowSimulationResult(
        times=np.asarray(simulator.tlist),
        expectations=expectations,
        labels=labels,
        shadow_hamiltonian=shadow_h,
        shadow_state=shadow_state,
        H_S_padded=H_S_padded,
        shadow_num_qubits=shadow_nq,
    )
