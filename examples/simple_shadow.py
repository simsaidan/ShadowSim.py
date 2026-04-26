"""
✅ Best test overall:  H = Z,  S = {X, Y}

✅ Then:  H = Z₁ + Z₂,  S = {XX, XY, YX, YY}

Uses the QuTiP-backed simulator and writes plots to ``results/``.

Run from the repository root::

    python examples/simple.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from src.core.hamiltonian import Hamiltonian
from src.core.operator_set import Operator, OperatorSet
from src.core.pauli import Pauli, PauliString
from src.core.state import State
from src.benchmarking.benchmark import Benchmark
from src.simulators.qutip_simulator import QutipSimulator
from src.shadow.shadow_hamiltonian import ShadowHamiltonian
from src.shadow.shadow_state import ShadowState


def _pauli_string_operator(label: str) -> Operator:
    m = PauliString.from_string(label).matrix()
    return Operator(m, name=label)


def hamiltonian_sum_z(num_qubits: int) -> Hamiltonian:
    """H = Σ_i Z_i (identity on all other qubits). For n=1 this is Z."""
    if num_qubits < 1:
        raise ValueError("num_qubits must be at least 1")
    z = Pauli("Z").matrix()
    i2 = np.eye(2, dtype=np.complex128)
    dim = 2**num_qubits
    H = np.zeros((dim, dim), dtype=np.complex128)
    for q in range(num_qubits):
        mats = [i2] * num_qubits
        mats[q] = z
        term = mats[0]
        for m in mats[1:]:
            term = np.kron(term, m)
        H += term
    return Hamiltonian(H)


def equal_superposition_state(num_qubits: int) -> State:
    """|+⟩^{⊗ n} with |+⟩ = (|0⟩+|1⟩)/√2 so observables have nontrivial dynamics."""
    plus = np.array([1, 1], dtype=np.complex128) / np.sqrt(2.0)
    psi = plus.copy()
    for _ in range(num_qubits - 1):
        psi = np.kron(psi, plus)
    return State(psi, num_qubits=num_qubits)


def run_benchmark_second_case(
    *,
    title: str,
    num_qubits: int,
    observable_labels: list[str],
    total_time: float = 6.29,
    time_steps: int = 200,
) -> None:
    H = hamiltonian_sum_z(num_qubits)
    operator_set = OperatorSet([_pauli_string_operator(s) for s in observable_labels])
    psi0 = equal_superposition_state(num_qubits)
    psi_shadow = ShadowState(psi0, operator_set)
    H_S = ShadowHamiltonian(operator_set, H)
    observables = [_pauli_string_operator(s) for s in observable_labels]
    sim_a = QutipSimulator([H], psi0, observables, num_qubits, total_time, time_steps)
    sim_b = QutipSimulator(
        [Hamiltonian(H_S.get_H_S())],
        psi_shadow,
        observables,
        num_qubits,
        total_time,
        time_steps,
    )
    bench = Benchmark(sim_a, sim_b)
    bench.run()
    paths = bench.save_result_plot(
        labels=observable_labels,
        title_a=f"{title} (run A)",
        title_b=f"{title} (run B)",
        title=f"|A − B| — {title}",
    )
    for path in paths:
        print(f"Saved: {path}")


def main() -> None:
    os.chdir(ROOT)
    run_benchmark_second_case(
        title="H = Z₁ + Z₂,  S = {XX, XY, YX, YY}",
        num_qubits=2,
        observable_labels=["XX", "XY", "YX", "YY"],
    )


if __name__ == "__main__":
    main()
