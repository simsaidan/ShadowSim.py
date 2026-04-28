from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from src.core.hamiltonian import Hamiltonian
from src.core.operator_set import Operator, OperatorSet
from src.core.pauli import PauliString
from src.simulators.qutip_simulator import QutipSimulator
from src.core.state import State
from src.shadow.shadow_hamiltonian import ShadowHamiltonian
from src.shadow.shadow_state import ShadowState


def pauli_word(label: str):
    return PauliString.from_string(label).matrix()


def z_projectors_2q() -> OperatorSet:
    labels = ("00", "01", "10", "11")
    ops: list[Operator] = []
    for i, lab in enumerate(labels):
        p = np.zeros((4, 4), dtype=np.complex128)
        p[i, i] = 1.0
        ops.append(Operator(p, name=f"P_{lab}"))
    return OperatorSet(ops)


# 3q sim: A, B (8×8).  Pairing chosen so the Pauli closure has |closure|=4 and H_S
# is not identically zero (XII+IIX drives mixing among single-qubit X,Y,Z on
# the left with IIX in the same 4D closed span).
hamiltonians = [
    Hamiltonian(pauli_word("XII")),
    Hamiltonian(pauli_word("IIX")),
]
observables = OperatorSet(
    [
        Operator(pauli_word("XII"), name="XII"),
        Operator(pauli_word("YII"), name="YII"),
        Operator(pauli_word("ZII"), name="ZII"),
        Operator(pauli_word("IIX"), name="IIX"),
    ]
)

print("Hamiltonians (A):", ["XII", "IIX"])
print("Observables (B):", [op.name for op in observables.operators])

initial_state = State(
    np.ones(8, dtype=np.complex128) / np.sqrt(8),
    3,
)

qutip_simulator = QutipSimulator(
    hamiltonians,
    [],
    initial_state,
    observables,
    3,
    5.0,
    400,
)

qutip_simulator.simulate()
qutip_simulator.plot_results(
    labels=[op.name for op in observables],
    title="3-qubit: B",
)

for op, trace in zip(observables, qutip_simulator.get_results(), strict=True):
    print(f"{op.name} variation:", float(np.max(trace) - np.min(trace)))

shadow_state = ShadowState(initial_state, observables)
print(shadow_state.to_numpy())
shadow_hamiltonian = ShadowHamiltonian(observables, hamiltonians, num_qubits=2)
print(shadow_hamiltonian.H_S)

shadow_e_ops = z_projectors_2q()
qutip2 = QutipSimulator(
    [Hamiltonian(np.asarray(shadow_hamiltonian.H_S, dtype=np.complex128))],
    [],
    shadow_state,
    shadow_e_ops,
    2,
    5.0,
    400,
)

qutip2.simulate()

for op, trace in zip(shadow_e_ops, qutip2.get_results(), strict=True):
    print(f"{op.name} variation:", float(np.max(trace) - np.min(trace)))

qutip2.plot_results(
    labels=[op.name for op in shadow_e_ops],
    title="2-qubit shadow",
)
