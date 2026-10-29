"""Open Jaynes–Cummings–Hubbard model factory.

``n_cavities=1`` matches ``jaynes_cummings``. More cavities add photon hopping.
"""

from dataclasses import dataclass, fields

import numpy as np

from shadowsim.models.tavis_cummings import (
    _DEFAULT_G,
    _DEFAULT_GAMMA,
    _DEFAULT_KAPPA,
    _DEFAULT_OMEGA_C,
    _DEFAULT_OMEGA_E,
)
from shadowsim.models.tavis_cummings_hubbard import TavisCummingsHubbardModel, tavis_cummings_hubbard


def _require_scalar(name: str, value: object) -> float:
    """Reject per-emitter sequences; each cavity has one emitter."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        raise ValueError(f"{name} must be a scalar for the Jaynes–Cummings–Hubbard model, got {type(value).__name__}")
    return float(value)


@dataclass(frozen=True)
class JaynesCummingsHubbardModel(TavisCummingsHubbardModel):
    """Bundled operators for the single-emitter Jaynes–Cummings–Hubbard open system.

    This is a ``TavisCummingsHubbardModel`` with ``n_emitters`` fixed at 1.
    Each cavity is two Fock qubits followed by one emitter, so ``num_qubits``
    is ``3 * n_cavities``.
    """

    def __post_init__(self) -> None:
        """Require one emitter on every cavity."""
        if self.n_emitters != 1 or self.num_qubits != 3 * self.n_cavities:
            raise ValueError(
                "JaynesCummingsHubbardModel is the single-emitter case: "
                "n_emitters must be 1 and num_qubits must be 3 * n_cavities, "
                f"got {self.n_emitters} and {self.num_qubits}"
            )


def jaynes_cummings_hubbard(
    *,
    omega_c: float = _DEFAULT_OMEGA_C,
    omega_e: float = _DEFAULT_OMEGA_E,
    kappa: float = _DEFAULT_KAPPA,
    gamma: float = _DEFAULT_GAMMA,
    g: float = _DEFAULT_G,
    n_cavities: int = 1,
    nu: object = 0.0,
    cavity_levels: int = 4,
    initial_fock: int = 2,
) -> JaynesCummingsHubbardModel:
    """Build an open Jaynes–Cummings–Hubbard model.

    Jaynes–Cummings–Hubbard is the one-emitter case of Tavis–Cummings–Hubbard.
    This factory calls ``tavis_cummings_hubbard(n_emitters=1, ...)`` and returns
    the same operators as a ``JaynesCummingsHubbardModel``. ``n_cavities=1``
    matches ``jaynes_cummings`` for the same arguments, and ``nu`` is unused.
    More cavities add the same photon hopping as ``tavis_cummings_hubbard``.

    ``kappa`` and ``gamma`` are Lindblad amplitudes, not decay rates.
    ``omega_e``, ``gamma``, and ``g`` are scalars; per-emitter sequences belong
    on ``tavis_cummings_hubbard``. ``nu`` may be one complex number for every
    pair, or a sequence of length ``n_cavities * (n_cavities - 1) / 2``.

    Args:
        omega_c: Cavity frequency, shared by every cavity.
        omega_e: Emitter frequency.
        kappa: Cavity Lindblad amplitude, shared by every cavity.
        gamma: Emitter Lindblad amplitude.
        g: Cavity–emitter coupling strength.
        n_cavities: Number of cavities (at least 1).
        nu: Photon hopping. One value for every cavity pair, or one value per
            pair ``q < p``.
        cavity_levels: Fock truncation. Must be 4.
        initial_fock: Initial cavity Fock occupation in ``0..3`` (every cavity
            starts there; every emitter starts in the ground state).

    Returns:
        A ``JaynesCummingsHubbardModel`` with full and local operators ready
        for simulators.

    Raises:
        ValueError: If ``omega_e``, ``gamma``, or ``g`` is not a scalar,
            ``n_cavities`` is not an integer of at least 1, ``cavity_levels``
            is not 4, ``initial_fock`` is outside ``0..3``, or ``nu`` does not
            match the number of cavity pairs.
    """
    omega_e_value = _require_scalar("omega_e", omega_e)
    gamma_value = _require_scalar("gamma", gamma)
    g_value = _require_scalar("g", g)
    base = tavis_cummings_hubbard(
        omega_c=omega_c,
        omega_e=omega_e_value,
        kappa=kappa,
        gamma=gamma_value,
        g=g_value,
        n_emitters=1,
        n_cavities=n_cavities,
        nu=nu,
        cavity_levels=cavity_levels,
        initial_fock=initial_fock,
    )
    # Copy fields by name. dataclasses.asdict would recurse and drop Hamiltonian
    # and Operator instances.
    return JaynesCummingsHubbardModel(
        **{field.name: getattr(base, field.name) for field in fields(TavisCummingsHubbardModel)}
    )
