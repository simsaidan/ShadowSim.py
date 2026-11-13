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
from shadowsim.models.tavis_cummings import (
    _DEFAULT_G,
    _DEFAULT_GAMMA,
    _DEFAULT_KAPPA,
    _DEFAULT_OMEGA_C,
    _DEFAULT_OMEGA_E,
    FloatOrSeq,
    TavisCummingsModel,
    _block_measurements,
    _cavity_block,
)
from shadowsim.simulators.reducers import Measurement
from shadowsim.utils.constants import I
from shadowsim.utils.tensor import tensor

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
    if isinstance(n_cavities, bool) or not isinstance(n_cavities, int) or n_cavities < 1:
        raise ValueError(f"n_cavities must be an integer >= 1, got {n_cavities}")

    n_pairs = n_cavities * (n_cavities - 1) // 2
    couplings = _pair_couplings(nu, n_pairs) if n_pairs else []
    block = _cavity_block(
        omega_c=omega_c,
        omega_e=omega_e,
        kappa=kappa,
        gamma=gamma,
        g=g,
        n_emitters=n_emitters,
        cavity_levels=cavity_levels,
        initial_fock=initial_fock,
    )
    block_qubits = 2 + n_emitters
    num_qubits = n_cavities * block_qubits

    local_hamiltonians: list[LocalHamiltonian] = []
    full_hamiltonians: list[Hamiltonian] = []
    c_ops_local: list[LocalOperator] = []
    c_ops_full: list[Operator] = []
    e_ops: list[Operator] = []
    measurements: list[Measurement] = []
    for cavity in range(n_cavities):
        offset = cavity * block_qubits
        right = num_qubits - offset - block_qubits
        for matrix, sites in block.local_hamiltonians:
            local_hamiltonians.append(LocalHamiltonian(matrix, [site + offset for site in sites]))
        for matrix in block.full_hamiltonians:
            full_hamiltonians.append(Hamiltonian(_embed_at(matrix, offset, right)))
        for matrix, sites in block.c_ops_local:
            c_ops_local.append(LocalOperator(matrix, [site + offset for site in sites]))
        for matrix in block.c_ops_full:
            c_ops_full.append(Operator(_embed_at(matrix, offset, right)))
        for matrix in block.e_ops:
            e_ops.append(Operator(_embed_at(matrix, offset, right)))
        measurements.extend(_block_measurements(offset, n_emitters))

    pair = 0
    for left_cavity in range(n_cavities):
        for right_cavity in range(left_cavity + 1, n_cavities):
            hopping = couplings[pair]
            pair += 1
            if hopping == 0:
                continue
            n_middle = (right_cavity - left_cavity) * block_qubits - 2
            hop = _hopping(block.lowering, hopping, n_middle)
            start = left_cavity * block_qubits
            end = right_cavity * block_qubits + 2
            local_hamiltonians.append(LocalHamiltonian(hop, list(range(start, end))))
            full_hamiltonians.append(Hamiltonian(_embed_at(hop, start, num_qubits - end)))

    psi0 = State(block.state if n_cavities == 1 else tensor([block.state] * n_cavities), num_qubits)
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
