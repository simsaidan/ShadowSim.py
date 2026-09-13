"""Open cavity–emitter (Tavis–Cummings–like) model factory."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.simulators.splitjmatrix_simulator import cavity_population, population_one
from shadowsim.utils.constants import (
    I,
    one_state_two_qubits,
    three_state_two_qubits,
    two_state_two_qubits,
    zero_state_two_qubits,
)
from shadowsim.utils.tensor import tensor

_DEFAULT_OMEGA_C = 245000.0
_DEFAULT_OMEGA_E = 245000.0
_DEFAULT_KAPPA = float(np.sqrt(24.5))
_DEFAULT_GAMMA = float(np.sqrt(0.4))
_DEFAULT_G = 100.0

_FOCK_STATES = (
    zero_state_two_qubits,
    one_state_two_qubits,
    two_state_two_qubits,
    three_state_two_qubits,
)

Reducer = Callable[[dict[str, int]], float]
FloatOrSeq = float | Sequence[float]


@dataclass(frozen=True)
class TavisCummingsModel:
    """Bundled operators and helpers for the cavity–emitter open system.

    Qubit layout is two cavity qubits (Fock truncation 4) followed by one qubit
    per emitter: sites ``[0, 1]`` then ``[2, ..., 1 + n_emitters]``.

    Attributes:
        full_hamiltonians: Hamiltonian terms embedded in the full Hilbert space
            (QuTiP path).
        local_hamiltonians: Hamiltonian terms on contiguous qubit blocks
            (Split-J path).
        c_ops_full: Lindblad operators in the full Hilbert space.
        c_ops_local: Lindblad operators on local qubit blocks.
        psi0: Initial state (cavity Fock ⊗ all emitters in ground).
        e_ops: Observables for QuTiP (cavity population, then each emitter).
        measurement_groups: Split-J groups after ancilla flip convention
            (cavity pair, then each emitter).
        reducers: Split-J count reducers matching ``e_ops``.
        num_qubits: ``2 + n_emitters``.
        n_emitters: Number of two-level emitters.
    """

    full_hamiltonians: list[Hamiltonian]
    local_hamiltonians: list[LocalHamiltonian]
    c_ops_full: list[Operator]
    c_ops_local: list[LocalOperator]
    psi0: State
    e_ops: list[Operator]
    measurement_groups: list[int | list[int]]
    reducers: Sequence[Reducer]
    num_qubits: int
    n_emitters: int


def _as_per_emitter(name: str, value: FloatOrSeq, n_emitters: int) -> list[float]:
    """Broadcast a scalar or validate a per-emitter sequence."""
    if isinstance(value, (int, float, np.floating)):
        return [float(value)] * n_emitters
    seq = [float(x) for x in value]
    if len(seq) != n_emitters:
        raise ValueError(f"{name} must be a scalar or a sequence of length {n_emitters}, got length {len(seq)}")
    return seq


def _pad_right(matrix: np.ndarray, n_identities: int) -> np.ndarray:
    """Tensor ``matrix`` on the left with ``n_identities`` copies of ``I`` on the right."""
    if n_identities == 0:
        return matrix
    return tensor([matrix, *([I] * n_identities)])


def _emitter_site(emitter_index: int) -> int:
    """Return the qubit index of emitter ``emitter_index`` (0-based)."""
    return 2 + emitter_index


def _cavity_emitter_coupling(a: np.ndarray, sigma: np.ndarray, emitter_index: int, g: float) -> np.ndarray:
    """Coupling ``g (a σ† + a† σ)`` on cavity plus emitter ``emitter_index``.

    Intermediate emitter sites (if any) are filled with identity so the support
    is the contiguous block ``[0, ..., 2 + emitter_index]``.
    """
    n_middle = emitter_index
    mid = [I] * n_middle
    sigma_up = sigma.conjugate().T
    return g * (tensor([a, *mid, sigma_up]) + tensor([a.conjugate().T, *mid, sigma]))


def _embed_on_emitter(op: np.ndarray, emitter_index: int, n_emitters: int) -> np.ndarray:
    """Embed a single-qubit operator on emitter ``emitter_index`` in the full space."""
    return tensor([I, I, *([I] * emitter_index), op, *([I] * (n_emitters - emitter_index - 1))])


def tavis_cummings(
    *,
    omega_c: float = _DEFAULT_OMEGA_C,
    omega_e: FloatOrSeq = _DEFAULT_OMEGA_E,
    kappa: float = _DEFAULT_KAPPA,
    gamma: FloatOrSeq = _DEFAULT_GAMMA,
    g: FloatOrSeq = _DEFAULT_G,
    n_emitters: int = 1,
    cavity_levels: int = 4,
    initial_fock: int = 2,
) -> TavisCummingsModel:
    """Build an open cavity–emitter (Tavis–Cummings–like) model.

    The cavity Fock space is truncated to four levels and encoded on two qubits;
    each emitter is a two-level system on its own qubit. Only ``cavity_levels=4``
    is supported in v1. ``n_emitters=1`` with default frequencies/couplings
    reproduces README Example 2 / ``examples/simple_algo_benchmark.py``.

    ``kappa`` and ``gamma`` are Lindblad amplitudes (as in the historical
    examples), not decay rates. ``omega_e``, ``gamma``, and ``g`` may be scalars
    (broadcast to every emitter) or sequences of length ``n_emitters``.

    Args:
        omega_c: Cavity frequency.
        omega_e: Emitter frequency (scalar or per-emitter).
        kappa: Cavity Lindblad amplitude.
        gamma: Emitter Lindblad amplitude (scalar or per-emitter).
        g: Cavity–emitter coupling strength (scalar or per-emitter).
        n_emitters: Number of emitters (at least 1).
        cavity_levels: Fock truncation. Must be 4.
        initial_fock: Initial cavity Fock occupation in ``0..3`` (emitters start
            in the ground state).

    Returns:
        A ``TavisCummingsModel`` with full and local operators ready for
        simulators.

    Raises:
        ValueError: If ``n_emitters < 1``, ``cavity_levels`` is not 4,
            ``initial_fock`` is outside ``0..3``, or a per-emitter sequence has
            the wrong length.
    """
    if n_emitters < 1:
        raise ValueError(f"n_emitters must be >= 1, got {n_emitters}")
    if cavity_levels != 4:
        raise ValueError(f"only cavity_levels=4 is supported in v1, got {cavity_levels}")
    if initial_fock not in (0, 1, 2, 3):
        raise ValueError(f"initial_fock must be an integer in 0..3, got {initial_fock}")

    omega_e_list = _as_per_emitter("omega_e", omega_e, n_emitters)
    gamma_list = _as_per_emitter("gamma", gamma, n_emitters)
    g_list = _as_per_emitter("g", g, n_emitters)

    a = (
        np.outer(zero_state_two_qubits, one_state_two_qubits)
        + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
        + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
    )

    zero = np.array([1, 0], dtype=np.complex128)
    one = np.array([0, 1], dtype=np.complex128)
    sigma = np.outer(zero, one)
    n_e = np.outer(one, one)
    num_qubits = 2 + n_emitters

    h_cavity = omega_c * a.conjugate().T @ a
    local_hamiltonians: list[LocalHamiltonian] = [LocalHamiltonian(h_cavity, [0, 1])]
    full_hamiltonians: list[Hamiltonian] = [Hamiltonian(_pad_right(h_cavity, n_emitters))]

    for i in range(n_emitters):
        site = _emitter_site(i)
        local_hamiltonians.append(LocalHamiltonian(omega_e_list[i] * n_e, [site]))
        full_hamiltonians.append(Hamiltonian(omega_e_list[i] * _embed_on_emitter(n_e, i, n_emitters)))

        coupling = _cavity_emitter_coupling(a, sigma, i, g_list[i])
        local_hamiltonians.append(LocalHamiltonian(coupling, list(range(0, site + 1))))
        full_hamiltonians.append(Hamiltonian(_pad_right(coupling, n_emitters - i - 1)))

    c_ops_local: list[LocalOperator] = [LocalOperator(kappa * a, [0, 1])]
    c_ops_full: list[Operator] = [Operator(_pad_right(kappa * a, n_emitters))]
    for i in range(n_emitters):
        site = _emitter_site(i)
        c_ops_local.append(LocalOperator(gamma_list[i] * sigma, [site]))
        c_ops_full.append(Operator(gamma_list[i] * _embed_on_emitter(sigma, i, n_emitters)))

    psi0 = State(tensor([_FOCK_STATES[initial_fock], *([zero] * n_emitters)]), num_qubits)

    e_ops = [Operator(_pad_right(a.conjugate().T @ a, n_emitters))]
    for i in range(n_emitters):
        e_ops.append(Operator(_embed_on_emitter(sigma.conjugate().T @ sigma, i, n_emitters)))

    # Split-J measures ancilla + body; after flip_dict, index 0 is ancilla,
    # [1, 2] are cavity qubits, and emitters start at index 3 (Example 2 convention).
    measurement_groups: list[int | list[int]] = [[1, 2], *range(3, 3 + n_emitters)]
    reducers: tuple[Reducer, ...] = (cavity_population, *((population_one,) * n_emitters))

    return TavisCummingsModel(
        full_hamiltonians=full_hamiltonians,
        local_hamiltonians=local_hamiltonians,
        c_ops_full=c_ops_full,
        c_ops_local=c_ops_local,
        psi0=psi0,
        e_ops=e_ops,
        measurement_groups=measurement_groups,
        reducers=reducers,
        num_qubits=num_qubits,
        n_emitters=n_emitters,
    )
