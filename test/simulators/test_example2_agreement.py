"""Integration check: reduced Example 2 setup, QuTiP vs SplitJMatrix agreement."""

import numpy as np
import pytest

from shadowsim.benchmarking import Benchmark
from shadowsim.core import (
    Hamiltonian,
    LocalHamiltonian,
    LocalOperator,
    Operator,
    State,
)
from shadowsim.simulators import (
    QutipSimulator,
    SplitJMatrixSimulator,
    cavity_population,
    population_one,
)
from shadowsim.utils import (
    I,
    one_state_two_qubits,
    tensor,
    three_state_two_qubits,
    two_state_two_qubits,
    zero_state_two_qubits,
)

# Reduced vs examples/simple_algo_benchmark.py (0.25, 301, num_steps=40, shots=10000).
TOTAL_TIME = 0.25
TIME_STEPS = 6
NUM_STEPS = 15
SHOTS = 1500

# QuTiP is deterministic. SplitJ disagreement is shot noise (~1/sqrt(shots) on
# empirical populations; cavity scales ~0-3) plus systematic split-J/Trotter
# bias that does not vanish with more shots. On this reduced config, local
# multi-trial max-abs errors were ~0.05; tolerances leave ~2-3x headroom so CI
# stays non-flaky while still catching order-of-magnitude regressions.
TOL_CAVITY = 0.15
TOL_EMITTER = 0.12


def _cavity_emitter_setup():
    """Minimal duplicate of Example 2 physics (cavity–emitter + Lindblad)."""
    omega_c = 245000
    omega_e = 245000
    kappa = np.sqrt(24.5)
    gamma = np.sqrt(0.4)
    g = 100

    a = (
        np.outer(zero_state_two_qubits, one_state_two_qubits)
        + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
        + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
    )

    zero = np.array([1, 0], dtype=np.complex128)
    one = np.array([0, 1], dtype=np.complex128)
    sigma = np.outer(zero, one)

    H1 = omega_c * a.conjugate().T @ a
    H2 = omega_e * np.outer(one, one)
    H3 = g * (np.kron(a, sigma.conjugate().T) + np.kron(a.conjugate().T, sigma))

    local_hamiltonians = [
        LocalHamiltonian(H1, [0, 1]),
        LocalHamiltonian(H2, [2]),
        LocalHamiltonian(H3, [0, 1, 2]),
    ]
    full_hamiltonians = [
        Hamiltonian(tensor([H1, I])),
        Hamiltonian(tensor([I, I, H2])),
        Hamiltonian(H3),
    ]

    L1_full = Operator(kappa * np.kron(a, I))
    L2_full = Operator(gamma * (tensor([I, I, sigma])))
    L1_local = LocalOperator(kappa * a, [0, 1])
    L2_local = LocalOperator(gamma * sigma, [2])

    psi_0 = State(tensor([two_state_two_qubits, zero]), 3)

    observables = [
        Operator(tensor([a.conjugate().T @ a, I])),
        Operator(tensor([I, I, sigma.conjugate().T @ sigma])),
    ]

    return {
        "local_hamiltonians": local_hamiltonians,
        "full_hamiltonians": full_hamiltonians,
        "lindblads_full": [L1_full, L2_full],
        "lindblads_local": [L1_local, L2_local],
        "psi_0": psi_0,
        "observables": observables,
    }


@pytest.mark.slow
def test_example2_qutip_splitjmatrix_agreement():
    setup = _cavity_emitter_setup()

    qutip_simulator = QutipSimulator(
        setup["full_hamiltonians"],
        setup["lindblads_full"],
        setup["psi_0"],
        setup["observables"],
        3,
        TOTAL_TIME,
        TIME_STEPS,
    )
    splitjmatrix_simulator = SplitJMatrixSimulator(
        setup["local_hamiltonians"],
        setup["lindblads_local"],
        setup["psi_0"],
        3,
        TOTAL_TIME,
        TIME_STEPS,
        NUM_STEPS,
        measurement_groups=[[1, 2], 3],
        reducers=[cavity_population, population_one],
        shots=SHOTS,
    )

    Benchmark(qutip_simulator, splitjmatrix_simulator).run()

    qutip_results = qutip_simulator.get_results()
    split_results = splitjmatrix_simulator.get_results()
    assert len(qutip_results) == len(split_results) == 2

    labels_and_tols = (
        ("cavity population", TOL_CAVITY),
        ("emitter population", TOL_EMITTER),
    )
    for index, (label, tol) in enumerate(labels_and_tols):
        qutip_curve = np.asarray(qutip_results[index], dtype=float)
        split_curve = np.asarray(split_results[index], dtype=float)
        max_abs = float(np.max(np.abs(qutip_curve - split_curve)))
        assert max_abs < tol, f"{label}: max abs error {max_abs:.4f} exceeds tolerance {tol}"
