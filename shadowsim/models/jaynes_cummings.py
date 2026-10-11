"""Open cavity–emitter (Jaynes–Cummings) model factory."""

from dataclasses import dataclass, fields

import numpy as np

from shadowsim.models.tavis_cummings import (
    _DEFAULT_G,
    _DEFAULT_GAMMA,
    _DEFAULT_KAPPA,
    _DEFAULT_OMEGA_C,
    _DEFAULT_OMEGA_E,
    TavisCummingsModel,
    tavis_cummings,
)


def _require_scalar(name: str, value: object) -> float:
    """Reject per-emitter sequences; Jaynes–Cummings has one emitter."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        raise ValueError(f"{name} must be a scalar for the Jaynes–Cummings model, got {type(value).__name__}")
    return float(value)


@dataclass(frozen=True)
class JaynesCummingsModel(TavisCummingsModel):
    """Bundled operators for the single-emitter Jaynes–Cummings open system.

    This is a ``TavisCummingsModel`` with ``n_emitters`` fixed at 1.
    Qubit layout is two cavity qubits (Fock truncation 4) followed by one
    emitter qubit: sites ``[0, 1]`` then ``[2]``.
    """

    def __post_init__(self) -> None:
        """Require the single-emitter qubit layout."""
        if self.n_emitters != 1 or self.num_qubits != 3:
            raise ValueError(
                "JaynesCummingsModel is the single-emitter case: "
                f"n_emitters must be 1 and num_qubits must be 3, got {self.n_emitters} and {self.num_qubits}"
            )


def jaynes_cummings(
    *,
    omega_c: float = _DEFAULT_OMEGA_C,
    omega_e: float = _DEFAULT_OMEGA_E,
    kappa: float = _DEFAULT_KAPPA,
    gamma: float = _DEFAULT_GAMMA,
    g: float = _DEFAULT_G,
    cavity_levels: int = 4,
    initial_fock: int = 2,
) -> JaynesCummingsModel:
    """Build an open cavity–emitter (Jaynes–Cummings) model.

    Jaynes–Cummings is the one-emitter case of Tavis–Cummings. This factory
    calls ``tavis_cummings(n_emitters=1, ...)`` and returns the same operators
    as a ``JaynesCummingsModel``. Defaults match README Example 2.

    ``kappa`` and ``gamma`` are Lindblad amplitudes (as in the historical
    examples), not decay rates. ``omega_e``, ``gamma``, and ``g`` are scalars;
    per-emitter sequences belong on ``tavis_cummings``.

    Args:
        omega_c: Cavity frequency.
        omega_e: Emitter frequency.
        kappa: Cavity Lindblad amplitude.
        gamma: Emitter Lindblad amplitude.
        g: Cavity–emitter coupling strength.
        cavity_levels: Fock truncation. Must be 4.
        initial_fock: Initial cavity Fock occupation in ``0..3`` (the emitter
            starts in the ground state).

    Returns:
        A ``JaynesCummingsModel`` with full and local operators ready for
        simulators.

    Raises:
        ValueError: If ``omega_e``, ``gamma``, or ``g`` is not a scalar,
            ``cavity_levels`` is not 4, or ``initial_fock`` is outside ``0..3``.
    """
    omega_e_value = _require_scalar("omega_e", omega_e)
    gamma_value = _require_scalar("gamma", gamma)
    g_value = _require_scalar("g", g)
    base = tavis_cummings(
        omega_c=omega_c,
        omega_e=omega_e_value,
        kappa=kappa,
        gamma=gamma_value,
        g=g_value,
        n_emitters=1,
        cavity_levels=cavity_levels,
        initial_fock=initial_fock,
    )
    # Copy fields by name. dataclasses.asdict would recurse and drop Hamiltonian
    # and Operator instances.
    return JaynesCummingsModel(**{f.name: getattr(base, f.name) for f in fields(TavisCummingsModel)})
