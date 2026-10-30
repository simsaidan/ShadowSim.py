"""Open cavity–emitter (Tavis–Cummings–Hubbard) model factory.

``n_cavities=1`` matches ``tavis_cummings``. More cavities add photon hopping.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeGuard, cast

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.models.tavis_cummings import TavisCummingsModel
from shadowsim.simulators.reducers import Measurement
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

FloatOrSeq = float | Sequence[float]
_Number = int | float | complex | np.number


@dataclass(frozen=True)
class TavisCummingsHubbardModel(TavisCummingsModel):
    """Bundled operators for the Tavis–Cummings–Hubbard open system.

    ``n_cavities`` blocks are concatenated. Each block is two cavity qubits
    (Fock truncation 4) followed by ``n_emitters`` emitter qubits, so
    ``n_emitters`` is the count on every cavity. ``num_qubits`` is
    ``n_cavities * (2 + n_emitters)``.
    """

    n_cavities: int = 1


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
    """Embed a single-qubit operator on emitter ``emitter_index`` in one cavity block."""
    return tensor([I, I, *([I] * emitter_index), op, *([I] * (n_emitters - emitter_index - 1))])


def _is_number(value: object) -> TypeGuard[_Number]:
    """Return whether ``value`` is a real or complex scalar."""
    return not isinstance(value, bool) and isinstance(value, _Number)


def _pair_couplings(nu: object, n_pairs: int) -> list[complex]:
    """Broadcast ``nu`` or validate one coupling per cavity pair."""
    if _is_number(nu):
        return [complex(cast(int | float | complex, nu))] * n_pairs
    if isinstance(nu, (str, bytes)) or not isinstance(nu, Sequence):
        raise ValueError(f"nu must be a scalar or a sequence of length {n_pairs}, got {type(nu).__name__}")
    couplings: list[complex] = []
    for item in nu:
        if not _is_number(item):
            raise ValueError(f"nu must be a scalar or a sequence of length {n_pairs}, got {type(nu).__name__}")
        couplings.append(complex(cast(int | float | complex, item)))
    if len(couplings) != n_pairs:
        raise ValueError(f"nu must be a scalar or a sequence of length {n_pairs}, got length {len(couplings)}")
    return couplings


def _embed_at(matrix: np.ndarray, left: int, right: int) -> np.ndarray:
    """Tensor ``matrix`` with ``left`` identities before it and ``right`` after it."""
    if left == 0 and right == 0:
        return matrix
    return tensor([*([I] * left), matrix, *([I] * right)])


def _hopping(a: np.ndarray, nu: complex, n_middle: int) -> np.ndarray:
    """Return ``nu a† ⊗ I ⊗ a + conjugate(nu) a ⊗ I ⊗ a†`` with ``n_middle`` identities."""
    middle = [I] * n_middle
    coupling = complex(nu)
    return coupling * tensor([a.conjugate().T, *middle, a]) + np.conjugate(coupling) * tensor(
        [a, *middle, a.conjugate().T]
    )


def tavis_cummings_hubbard(
    *,
    omega_c: float = _DEFAULT_OMEGA_C,
    omega_e: FloatOrSeq = _DEFAULT_OMEGA_E,
    kappa: float = _DEFAULT_KAPPA,
    gamma: FloatOrSeq = _DEFAULT_GAMMA,
    g: FloatOrSeq = _DEFAULT_G,
    n_emitters: int = 1,
    n_cavities: int = 1,
    nu: object = 0.0,
    cavity_levels: int = 4,
    initial_fock: int = 2,
) -> TavisCummingsHubbardModel:
    """Build an open Tavis–Cummings–Hubbard model.

    ``n_cavities`` copies of a Tavis–Cummings system sit on consecutive qubit
    blocks. ``n_cavities=1`` matches ``tavis_cummings`` for the same arguments,
    and ``nu`` is unused. Each later pair of cavities ``q < p``, in
    lexicographic order, may add the hopping
    ``nu a_q† a_p + conjugate(nu) a_q a_p†``. A zero coupling is omitted.
    Only ``cavity_levels=4`` is supported in v1. The one-emitter case is
    ``jaynes_cummings_hubbard``. ``n_emitters=1`` with one cavity and the
    default frequencies reproduces README Example 2.

    ``kappa`` and ``gamma`` are Lindblad amplitudes (as in the historical
    examples), not decay rates. ``omega_e``, ``gamma``, and ``g`` may be scalars
    (broadcast to every emitter of every cavity) or sequences of length
    ``n_emitters``. ``nu`` may be one complex number for every pair, or a
    sequence of length ``n_cavities * (n_cavities - 1) / 2``.

    Args:
        omega_c: Cavity frequency, shared by every cavity.
        omega_e: Emitter frequency (scalar or per-emitter within a cavity).
        kappa: Cavity Lindblad amplitude, shared by every cavity.
        gamma: Emitter Lindblad amplitude (scalar or per-emitter within a cavity).
        g: Cavity–emitter coupling strength (scalar or per-emitter within a cavity).
        n_emitters: Emitters on every cavity (at least 1).
        n_cavities: Number of cavities (at least 1).
        nu: Photon hopping. One value for every cavity pair, or one value per
            pair ``q < p``.
        cavity_levels: Fock truncation. Must be 4.
        initial_fock: Initial cavity Fock occupation in ``0..3`` (every cavity
            starts there; emitters start in the ground state).

    Returns:
        A ``TavisCummingsHubbardModel`` with full and local operators ready for
        simulators.

    Raises:
        ValueError: If ``n_emitters < 1``, ``n_cavities`` is not an integer of
            at least 1, ``cavity_levels`` is not 4, ``initial_fock`` is outside
            ``0..3``, a per-emitter sequence has the wrong length, or ``nu``
            does not match the number of cavity pairs.
    """
    if n_emitters < 1:
        raise ValueError(f"n_emitters must be >= 1, got {n_emitters}")
    if isinstance(n_cavities, bool) or not isinstance(n_cavities, int) or n_cavities < 1:
        raise ValueError(f"n_cavities must be an integer >= 1, got {n_cavities}")
    if cavity_levels != 4:
        raise ValueError(f"only cavity_levels=4 is supported in v1, got {cavity_levels}")
    if initial_fock not in (0, 1, 2, 3):
        raise ValueError(f"initial_fock must be an integer in 0..3, got {initial_fock}")

    omega_e_list = _as_per_emitter("omega_e", omega_e, n_emitters)
    gamma_list = _as_per_emitter("gamma", gamma, n_emitters)
    g_list = _as_per_emitter("g", g, n_emitters)
    n_pairs = n_cavities * (n_cavities - 1) // 2
    couplings = _pair_couplings(nu, n_pairs) if n_pairs else []

    a = (
        np.outer(zero_state_two_qubits, one_state_two_qubits)
        + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
        + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
    )

    zero = np.array([1, 0], dtype=np.complex128)
    one = np.array([0, 1], dtype=np.complex128)
    sigma = np.outer(zero, one)
    n_e = np.outer(one, one)
    block_qubits = 2 + n_emitters
    num_qubits = n_cavities * block_qubits

    h_cavity = omega_c * a.conjugate().T @ a
    block_local: list[tuple[np.ndarray, list[int]]] = [(h_cavity, [0, 1])]
    block_full: list[np.ndarray] = [_pad_right(h_cavity, n_emitters)]
    for i in range(n_emitters):
        site = _emitter_site(i)
        block_local.append((omega_e_list[i] * n_e, [site]))
        block_full.append(omega_e_list[i] * _embed_on_emitter(n_e, i, n_emitters))
        exchange = _cavity_emitter_coupling(a, sigma, i, g_list[i])
        block_local.append((exchange, list(range(0, site + 1))))
        block_full.append(_pad_right(exchange, n_emitters - i - 1))

    block_c_local: list[tuple[np.ndarray, list[int]]] = [(kappa * a, [0, 1])]
    block_c_full: list[np.ndarray] = [_pad_right(kappa * a, n_emitters)]
    for i in range(n_emitters):
        site = _emitter_site(i)
        block_c_local.append((gamma_list[i] * sigma, [site]))
        block_c_full.append(gamma_list[i] * _embed_on_emitter(sigma, i, n_emitters))

    block_e_ops = [_pad_right(a.conjugate().T @ a, n_emitters)]
    for i in range(n_emitters):
        block_e_ops.append(_embed_on_emitter(sigma.conjugate().T @ sigma, i, n_emitters))
    block_state = tensor([_FOCK_STATES[initial_fock], *([zero] * n_emitters)])

    local_hamiltonians: list[LocalHamiltonian] = []
    full_hamiltonians: list[Hamiltonian] = []
    c_ops_local: list[LocalOperator] = []
    c_ops_full: list[Operator] = []
    e_ops: list[Operator] = []
    measurements: list[Measurement] = []
    for cavity in range(n_cavities):
        offset = cavity * block_qubits
        right = num_qubits - offset - block_qubits
        for matrix, sites in block_local:
            local_hamiltonians.append(LocalHamiltonian(matrix, [site + offset for site in sites]))
        for matrix in block_full:
            full_hamiltonians.append(Hamiltonian(_embed_at(matrix, offset, right)))
        for matrix, sites in block_c_local:
            c_ops_local.append(LocalOperator(matrix, [site + offset for site in sites]))
        for matrix in block_c_full:
            c_ops_full.append(Operator(_embed_at(matrix, offset, right)))
        for matrix in block_e_ops:
            e_ops.append(Operator(_embed_at(matrix, offset, right)))
        measurements.append(Measurement.cavity_population(offset, offset + 1))
        measurements.extend(Measurement.population(offset + _emitter_site(i)) for i in range(n_emitters))

    pair = 0
    for left_cavity in range(n_cavities):
        for right_cavity in range(left_cavity + 1, n_cavities):
            hopping = couplings[pair]
            pair += 1
            if hopping == 0:
                continue
            n_middle = (right_cavity - left_cavity) * block_qubits - 2
            hop = _hopping(a, hopping, n_middle)
            start = left_cavity * block_qubits
            end = right_cavity * block_qubits + 2
            local_hamiltonians.append(LocalHamiltonian(hop, list(range(start, end))))
            full_hamiltonians.append(Hamiltonian(_embed_at(hop, start, num_qubits - end)))

    psi0 = State(block_state if n_cavities == 1 else tensor([block_state] * n_cavities), num_qubits)

    return TavisCummingsHubbardModel(
        full_hamiltonians=full_hamiltonians,
        local_hamiltonians=local_hamiltonians,
        c_ops_full=c_ops_full,
        c_ops_local=c_ops_local,
        psi0=psi0,
        e_ops=e_ops,
        measurements=measurements,
        num_qubits=num_qubits,
        n_emitters=n_emitters,
        n_cavities=n_cavities,
    )
