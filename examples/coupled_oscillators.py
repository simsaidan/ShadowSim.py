"""Coupled oscillators: Newton, Babbush, shadow, and a truncated Fock space.

Newton's equations are the reference. Babbush et al. (arXiv:2303.13012, Eq. 12)
store velocities and spring extensions in one block Hamiltonian. Somma et al.
(arXiv:2407.21775, Sec. 2) recover the same expectations from a shadow state
evolved by ``change_of_basis(Γ).H_S``. A QuTiP run on the truncated Fock space
is the standard simulation those two registers replace.

The shared quantity is the semiclassical kinetic-energy fraction of the first
mass, built from momentum (or ``⟨P⟩``), not from ``⟨P²⟩``. Three modes at Fock
cutoff 8 need 9 qubits. Cutoff 4 is only 6 qubits, but on this network the
truncated ladder does not stay on the classical trajectory. The Babbush state
and the shadow Hamiltonian both have dimension 6 and pad to 3 qubits.

``run_shadow_simulation`` is the wrong tool here: it closes Pauli operators on
the Fock register. The bosonic shadow is the 6-by-6 matrix from ``change_of_basis``.
"""

import numpy as np
import numpy.typing as npt
from matplotlib import pyplot as plt

from shadowsim.core import Hamiltonian, Operator, State
from shadowsim.shadow import change_of_basis
from shadowsim.simulators import QutipSimulator
from shadowsim.utils.next_power_of_two import next_power_of_two

N_MASSES = 3
MASSES = np.ones(N_MASSES)
WALLS = np.array([1.0, 0.0, 1.0])
COUPLINGS = ((0, 1, 0.5), (1, 2, 0.4))
X0 = np.zeros(N_MASSES)
V0 = np.array([1.0, 0.0, 0.0])
# Cutoff 4 (6 qubits) drifts off the classical trajectory. Cutoff 8 is 9 qubits.
# Past t = 2 the truncated ladder's position error grows past about 1e-3.
FOCK_CUTOFF = 8
TOTAL_TIME = 2.0
TIME_STEPS = 401
# First mass. Babbush's kinetic fraction is the probability of this basis vector.
KINETIC_INDEX = 0


def register_qubits(dimension: int) -> int:
    """Return the qubits needed to pad ``dimension`` up to a power of two."""
    return next_power_of_two(dimension).bit_length() - 1


def spring_matrix(
    walls: npt.NDArray[np.float64], couplings: tuple[tuple[int, int, float], ...]
) -> npt.NDArray[np.float64]:
    """Return the grounded graph Laplacian ``F`` for wall and coupling springs."""
    size = walls.shape[0]
    spring = np.diag(walls.astype(np.float64, copy=True))
    for left, right, kappa in couplings:
        spring[left, left] += kappa
        spring[right, right] += kappa
        spring[left, right] -= kappa
        spring[right, left] -= kappa
    return spring


def stiffness_matrix(masses: npt.NDArray[np.float64], spring: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Return ``A = M^{-1/2} F M^{-1/2}`` from Newton's equation ``ÿ = -A y``."""
    scale = np.sqrt(np.outer(masses, masses))
    return spring / scale


def total_energy(
    masses: npt.NDArray[np.float64],
    spring: npt.NDArray[np.float64],
    positions: npt.NDArray[np.float64],
    velocities: npt.NDArray[np.float64],
) -> float:
    """Return ``K + U`` for one phase-space point."""
    kinetic = 0.5 * float(np.dot(masses, velocities**2))
    potential = 0.5 * float(positions @ spring @ positions)
    return kinetic + potential


def kinetic_fraction(
    momenta: npt.NDArray[np.float64],
    masses: npt.NDArray[np.float64],
    energy: float,
    index: int,
) -> npt.NDArray[np.float64]:
    """Return ``K_index(t) / E`` from ``p_index(t)² / (2 m E)``."""
    column = momenta[:, index]
    return (column**2) / (2.0 * masses[index] * energy)


def evolve_hermitian(
    generator: npt.NDArray[np.complexfloating],
    initial: npt.NDArray[np.complexfloating],
    times: npt.NDArray[np.float64],
) -> npt.NDArray[np.complexfloating]:
    """Return ``exp(-i G t) initial`` at each time. ``G`` is Hermitian."""
    eigenvalues, eigenvectors = np.linalg.eigh(generator)
    coefficients = eigenvectors.conj().T @ initial
    phases = np.exp(-1j * eigenvalues[:, None] * times[None, :])
    return eigenvectors @ (coefficients[:, None] * phases)


def newton_trajectory(
    times: npt.NDArray[np.float64],
    masses: npt.NDArray[np.float64],
    spring: npt.NDArray[np.float64],
    positions0: npt.NDArray[np.float64],
    velocities0: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return positions and momenta from the normal modes of ``ÿ = -A y``."""
    scale = np.sqrt(masses)
    displacement = scale * positions0
    velocity = scale * velocities0
    eigenvalues, eigenvectors = np.linalg.eigh(stiffness_matrix(masses, spring))
    if np.min(eigenvalues) <= 0.0:
        raise ValueError("spring matrix must be positive definite")
    omega = np.sqrt(eigenvalues)
    phase = omega[:, None] * times[None, :]
    displacement_mode = eigenvectors.T @ displacement
    velocity_mode = eigenvectors.T @ velocity
    displacement_t = (
        displacement_mode[:, None] * np.cos(phase) + velocity_mode[:, None] * np.sin(phase) / omega[:, None]
    )
    velocity_t = -displacement_mode[:, None] * omega[:, None] * np.sin(phase) + velocity_mode[:, None] * np.cos(phase)
    positions = ((eigenvectors @ displacement_t) / scale[:, None]).T
    momenta = ((eigenvectors @ velocity_t) * scale[:, None]).T
    return positions.real, momenta.real


def babbush_trajectory(
    times: npt.NDArray[np.float64],
    masses: npt.NDArray[np.float64],
    spring: npt.NDArray[np.float64],
    positions0: npt.NDArray[np.float64],
    velocities0: npt.NDArray[np.float64],
    energy: float,
    index: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Evolve the block encoding whose first amplitudes are rescaled velocities.

    ``H = -[[0, sqrt(A)], [sqrt(A), 0]]`` and
    ``|ψ⟩ = [ẏ; i sqrt(A) y] / sqrt(2E)``. ``|ψ_index|²`` is ``K_index / E``.
    """
    scale = np.sqrt(masses)
    displacement = scale * positions0
    velocity = scale * velocities0
    eigenvalues, eigenvectors = np.linalg.eigh(stiffness_matrix(masses, spring))
    if np.min(eigenvalues) <= 0.0:
        raise ValueError("spring matrix must be positive definite")
    sqrt_a = (eigenvectors * np.sqrt(eigenvalues)) @ eigenvectors.T
    zeros = np.zeros_like(sqrt_a)
    block = -np.block([[zeros, sqrt_a], [sqrt_a.T, zeros]])
    sqrt_2e = np.sqrt(2.0 * energy)
    initial = np.concatenate([velocity, 1j * (sqrt_a.T @ displacement)]) / sqrt_2e
    evolved = evolve_hermitian(block, initial.astype(np.complex128), times)
    recovered_velocity = sqrt_2e * evolved[: masses.shape[0]]
    recovered_displacement = np.linalg.solve(sqrt_a.T, -1j * sqrt_2e * evolved[masses.shape[0] :])
    positions = (recovered_displacement.real / scale[:, None]).T
    momenta = (recovered_velocity.real * scale[:, None]).T
    probability = np.abs(evolved[index]) ** 2
    fraction = kinetic_fraction(momenta, masses, energy, index)
    if not np.allclose(probability, fraction, atol=1e-8):
        raise RuntimeError("Babbush basis probability disagrees with the recovered kinetic fraction")
    return positions, momenta


def shadow_trajectory(
    times: npt.NDArray[np.float64],
    masses: npt.NDArray[np.float64],
    spring: npt.NDArray[np.float64],
    positions0: npt.NDArray[np.float64],
    velocities0: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], int]:
    """Evolve ``⟨O⟩ = B† ⟨Y⟩`` under ``H_S`` and invert back to ``⟨P⟩`` and ``⟨Q⟩``.

    ``Y = (P, Q)`` and ``Γ = diag(M^{-1}, F)``. Returns positions, momenta, and
    the unpadded shadow dimension.
    """
    size = masses.shape[0]
    gamma = np.zeros((2 * size, 2 * size), dtype=np.float64)
    gamma[:size, :size] = np.diag(1.0 / masses)
    gamma[size:, size:] = spring
    if np.min(np.linalg.eigvalsh(gamma)) <= 0.0:
        raise ValueError("gamma must be positive definite so expectations can be inverted")
    basis = change_of_basis(gamma)
    expectations = basis.A @ np.concatenate([masses * velocities0, positions0])
    evolved = evolve_hermitian(basis.H_S, expectations.astype(np.complex128), times)
    recovered = np.linalg.solve(basis.A, evolved)
    momenta = recovered[:size].real.T
    positions = recovered[size:].real.T
    return positions, momenta, int(basis.H_S.shape[0])


def _mode_annihilation(cutoff: int) -> npt.NDArray[np.complex128]:
    """Return the truncated ``a`` with ``a|n⟩ = sqrt(n)|n-1⟩``."""
    operator = np.zeros((cutoff, cutoff), dtype=np.complex128)
    for level in range(1, cutoff):
        operator[level - 1, level] = np.sqrt(level)
    return operator


def _embed_mode(local: npt.NDArray[np.complex128], mode: int, n_modes: int, cutoff: int) -> npt.NDArray[np.complex128]:
    """Place a single-mode operator on mode ``mode`` of a product Fock space."""
    left = np.eye(cutoff**mode, dtype=np.complex128)
    right = np.eye(cutoff ** (n_modes - mode - 1), dtype=np.complex128)
    return np.kron(np.kron(left, local), right)


def _coherent_amplitudes(alpha: complex, cutoff: int) -> npt.NDArray[np.complex128]:
    """Return a cutoff coherent state with ``⟨Q⟩ + i⟨P⟩ = sqrt(2) α``, renormalized."""
    amplitudes = np.zeros(cutoff, dtype=np.complex128)
    amplitudes[0] = np.exp(-0.5 * abs(alpha) ** 2)
    for level in range(1, cutoff):
        amplitudes[level] = amplitudes[level - 1] * alpha / np.sqrt(level)
    return amplitudes / np.linalg.norm(amplitudes)


def fock_trajectory(
    times: npt.NDArray[np.float64],
    masses: npt.NDArray[np.float64],
    spring: npt.NDArray[np.float64],
    positions0: npt.NDArray[np.float64],
    velocities0: npt.NDArray[np.float64],
    cutoff: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Evolve a product of coherent states in a truncated Fock space with QuTiP.

    Each mode uses ``Q = (a + a†) / sqrt(2)`` and ``P = -i (a - a†) / sqrt(2)``.
    The initial displacement matches ``positions0`` and ``masses * velocities0``.
    """
    n_modes = masses.shape[0]
    dimension = cutoff**n_modes
    if dimension.bit_count() != 1:
        raise ValueError(f"cutoff**n_modes must be a power of two so the space is qubits, got {dimension}")
    annihilation = _mode_annihilation(cutoff)
    creation = annihilation.conj().T
    position = (annihilation + creation) / np.sqrt(2.0)
    momentum = -1j * (annihilation - creation) / np.sqrt(2.0)
    q_ops = [_embed_mode(position, mode, n_modes, cutoff) for mode in range(n_modes)]
    p_ops = [_embed_mode(momentum, mode, n_modes, cutoff) for mode in range(n_modes)]

    hamiltonian = sum((p_ops[mode] @ p_ops[mode]) / (2.0 * masses[mode]) for mode in range(n_modes))
    for row in range(n_modes):
        for column in range(n_modes):
            hamiltonian = hamiltonian + 0.5 * spring[row, column] * (q_ops[row] @ q_ops[column])
    hamiltonian = 0.5 * (hamiltonian + hamiltonian.conj().T)

    alphas = (positions0 + 1j * (masses * velocities0)) / np.sqrt(2.0)
    amplitude = _coherent_amplitudes(complex(alphas[0]), cutoff)
    for alpha in alphas[1:]:
        amplitude = np.kron(amplitude, _coherent_amplitudes(complex(alpha), cutoff))

    observables = [Operator(q_ops[mode], name=f"Q{mode}") for mode in range(n_modes)]
    observables.extend(Operator(p_ops[mode], name=f"P{mode}") for mode in range(n_modes))
    simulator = QutipSimulator(
        [Hamiltonian(hamiltonian)],
        [],
        State(amplitude, dimension.bit_length() - 1),
        observables,
        num_qubits=dimension.bit_length() - 1,
        total_time=float(times[-1]),
        time_steps=times.shape[0],
    )
    traces = simulator.simulate().observables
    positions = np.stack([np.real(traces[mode]) for mode in range(n_modes)], axis=1)
    momenta = np.stack([np.real(traces[n_modes + mode]) for mode in range(n_modes)], axis=1)
    return positions, momenta


def _max_abs(reference: npt.NDArray[np.float64], other: npt.NDArray[np.float64]) -> float:
    return float(np.max(np.abs(reference - other)))


def main() -> None:
    """Print qubit counts and trajectory errors, then plot ``K_0(t) / E``."""
    times = np.linspace(0.0, TOTAL_TIME, TIME_STEPS)
    spring = spring_matrix(WALLS, COUPLINGS)
    energy = total_energy(MASSES, spring, X0, V0)
    newton_x, newton_p = newton_trajectory(times, MASSES, spring, X0, V0)
    babbush_x, babbush_p = babbush_trajectory(times, MASSES, spring, X0, V0, energy, KINETIC_INDEX)
    shadow_x, shadow_p, shadow_dimension = shadow_trajectory(times, MASSES, spring, X0, V0)
    fock_x, fock_p = fock_trajectory(times, MASSES, spring, X0, V0, FOCK_CUTOFF)

    fock_dimension = FOCK_CUTOFF**N_MASSES
    curves = {
        "Babbush": (babbush_x, babbush_p),
        "shadow": (shadow_x, shadow_p),
        "QuTiP": (fock_x, fock_p),
    }
    fractions = {"Newton": kinetic_fraction(newton_p, MASSES, energy, KINETIC_INDEX)}
    for name, (_positions, momenta) in curves.items():
        fractions[name] = kinetic_fraction(momenta, MASSES, energy, KINETIC_INDEX)

    print(f"Fock register: {register_qubits(fock_dimension)} qubits (dimension {fock_dimension})")
    print(
        f"Babbush register: {register_qubits(2 * N_MASSES)} qubits "
        f"(dimension {2 * N_MASSES}, padded to {next_power_of_two(2 * N_MASSES)})"
    )
    print(
        f"shadow register: {register_qubits(shadow_dimension)} qubits "
        f"(dimension {shadow_dimension}, padded to {next_power_of_two(shadow_dimension)})"
    )
    print(f"total energy E = {energy:.6f}")
    for name, (positions, momenta) in curves.items():
        print(
            f"{name} max |x - Newton| = {_max_abs(newton_x, positions):.3e}, "
            f"max |p - Newton| = {_max_abs(newton_p, momenta):.3e}, "
            f"max |K/E - Newton| = {_max_abs(fractions['Newton'], fractions[name]):.3e}"
        )

    fock_qubits = register_qubits(fock_dimension)
    encoded_qubits = register_qubits(shadow_dimension)
    plt.plot(times, fractions["Newton"], label="Newton")
    plt.plot(times, fractions["Babbush"], linestyle="--", label=f"Babbush ({encoded_qubits} qubits)")
    plt.plot(times, fractions["shadow"], linestyle=":", label=f"shadow ({encoded_qubits} qubits)")
    plt.plot(times, fractions["QuTiP"], linestyle="-.", label=f"QuTiP Fock ({fock_qubits} qubits)")
    plt.xlabel("Time")
    plt.ylabel("K / E")
    plt.title(f"First-mass kinetic fraction: Fock {fock_qubits} qubits, encoded {encoded_qubits} qubits")
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
