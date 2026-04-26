from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.utils import (
    zero_state_two_qubits,
    one_state_two_qubits,
    two_state_two_qubits,
    three_state_two_qubits,
    tensor,
    I,
)

from src.benchmarking.benchmark import Benchmark
from src.core.hamiltonian import LocalHamiltonian, Hamiltonian
from src.simulators.qutip_simulator import QutipSimulator
from src.simulators.splitjmatrix_simulator import (
    SplitJMatrixSimulator,
    _cavity_population,
    _population_one,
)
from src.core.state import State
from src.core.operator_set import LocalOperator, Operator

# Define system parameters
omega_c = 245000
omega_e = 245000
kappa = np.sqrt(24.5)
gamma = np.sqrt(0.4)
g = 100


# Define Hamiltonians
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

# Define Lindblad operators
L1_full = Operator(kappa * np.kron(a, I))
L2_full = Operator(gamma * (tensor([I, I, sigma])))
L1_local = LocalOperator(kappa * a, [0, 1])
L2_local = LocalOperator(gamma * sigma, [2])

# Define initial state
psi_0 = State(tensor([two_state_two_qubits, zero]), 3)

# Run qutip simulator
qutip_simulator = QutipSimulator(
    full_hamiltonians,
    [L1_full, L2_full],
    psi_0,
    [
        Operator(tensor([a.conjugate().T @ a, I])),
        Operator(tensor([I, I, sigma.conjugate().T @ sigma])),
    ],
    3,
    0.25,
    100,
)
# Run Split JMatrix simulator
splitjmatrix_simulator = SplitJMatrixSimulator(
    local_hamiltonians,
    [L1_local, L2_local],
    psi_0,
    3,
    0.25,
    100,
    30,
    measurement_groups=[[1, 2], 3],
    reducers=[_cavity_population, _population_one],
)

# Run benchmark
benchmark = Benchmark(qutip_simulator, splitjmatrix_simulator)
benchmark.run()
paths = benchmark.save_result_plot(labels=["cavity population", "emitter population"])
for path in paths:
    print(f"Saved: {path}")
