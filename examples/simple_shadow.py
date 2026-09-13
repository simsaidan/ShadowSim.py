import numpy as np
from matplotlib import pyplot as plt

from shadowsim.core import Hamiltonian, OperatorSet, State
from shadowsim.shadow import run_shadow_simulation
from shadowsim.simulators import QutipSimulator

# 3q sim: A, B (8×8).  Pairing chosen so the Pauli closure has |closure|=4 and H_S
# is not identically zero (XII+IIX drives mixing among single-qubit X,Y,Z on
# the left with IIX in the same 4D closed span).
hamiltonians = [
    Hamiltonian("XII"),
    Hamiltonian("IIX"),
]
observables = OperatorSet(["XII", "YII", "ZII", "IIX"])

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

shadow = run_shadow_simulation(
    hamiltonians,
    observables,
    initial_state,
    total_time=5.0,
    time_steps=400,
)
print("shadow state:", shadow.shadow_state.to_numpy())
print("H_S:", shadow.shadow_hamiltonian.H_S)
print("shadow_num_qubits:", shadow.shadow_num_qubits)

for label, trace in zip(shadow.labels, shadow.expectations, strict=True):
    print(f"{label} variation:", float(np.max(trace) - np.min(trace)))

for label, trace in zip(shadow.labels, shadow.expectations, strict=True):
    plt.plot(shadow.times, trace, label=label)
plt.title(f"{shadow.shadow_num_qubits}-qubit shadow")
plt.xlabel("Time")
plt.ylabel("Expectation")
plt.legend()
plt.show()
