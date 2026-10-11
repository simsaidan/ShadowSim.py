"""Encode classical data and evolve one of the states with QuTiP."""

import numpy as np

from shadowsim.core import Hamiltonian, OperatorSet
from shadowsim.encoding import AmplitudeEncoding, AngleEncoding, ComputationalBasisEncoding
from shadowsim.simulators import QutipSimulator

basis = ComputationalBasisEncoding(2).encode([1, 0])
angle = AngleEncoding().encode([np.pi / 2, 0.0])
amplitude = AmplitudeEncoding().encode([1.0, 1.0, 0.0])

print("basis qubits:", basis.get_num_qubits())
print("basis state:", np.round(basis.to_numpy(), decimals=8))
print("angle state:", np.round(angle.to_numpy(), decimals=8))
print("amplitude qubits:", amplitude.get_num_qubits())
print("amplitude state:", np.round(amplitude.to_numpy(), decimals=8))

simulator = QutipSimulator(
    [Hamiltonian("XI"), Hamiltonian("IX")],
    [],
    amplitude,
    OperatorSet(["ZI", "IZ"]),
    num_qubits=amplitude.get_num_qubits(),
    total_time=1.0,
    time_steps=21,
)
result = simulator.simulate()

for label, trace in zip(["ZI", "IZ"], result.observables, strict=True):
    print(f"<{label}> final: {float(trace[-1]):.6f}")
