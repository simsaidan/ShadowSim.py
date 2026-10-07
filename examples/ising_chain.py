"""Simulate a small transverse-field Ising chain with QuTiP."""

from shadowsim.models import ising
from shadowsim.simulators import QutipSimulator

# Open TFIM chain: H = J Σ Z_i Z_j + h Σ X_i
model = ising(
    n_qubits=4,
    J=1.0,
    h=0.5,
    field="transverse",
    topology="chain",
    boundary="open",
)

print("edges:", model.edges)
print("H:", model.pauli_sum)

simulator = QutipSimulator(
    model.full_hamiltonians,
    model.c_ops_full,
    model.psi0,
    model.e_ops,
    model.num_qubits,
    2.0,
    101,
)
result = simulator.simulate()

for i, trace in enumerate(result.observables):
    print(f"<Z_{i}> final: {float(trace[-1]):.6f}")

# Classical Ising (longitudinal field) and custom connectivity are available too:
_classical = ising(n_qubits=4, J=1.0, h=0.25, field="classical")
_custom = ising(
    n_qubits=4,
    J=1.0,
    h=0.5,
    field="transverse",
    edges=[(0, 1), (1, 2), (2, 3), (0, 2)],
)
print("classical edges:", _classical.edges, "field:", _classical.field)
print("custom edges:", _custom.edges, "topology:", _custom.topology)
