from src.core.hamiltonian import Hamiltonian, LocalHamiltonian
from src.core.state import State
from src.simulators.simulator import Simulator
from src.core.operator_set import Operator, LocalOperator
from qiskit import QuantumCircuit, transpile, QuantumRegister
from qiskit.circuit.library import UnitaryGate
from qiskit_aer import AerSimulator
import scipy
import numpy as np
from typing import Callable, List
from src.core.utils import flip_dict


def _trace_qubits(
    counts: dict[str, int], qubit_indices: int | List[int] | List[int | List[int]]
) -> dict[str, int] | list[dict[str, int]]:
    """
    Marginalize measurement counts over selected qubits.

    Supports:
      - int:          `2`
      - list[int]:    `[0, 1]`
      - grouped list: `[[0, 1], 2]` -> returns one counts dict per group
    """

    def _single_group(indices: list[int]) -> dict[str, int]:
        res: dict[str, int] = {}
        for bitstring, shot_count in counts.items():
            projected = "".join(bitstring[i] for i in indices)
            res[projected] = res.get(projected, 0) + shot_count
        return res

    if isinstance(qubit_indices, int):
        return _single_group([qubit_indices])

    items = list(qubit_indices)
    is_grouped = any(isinstance(item, list) for item in items)
    if not is_grouped:
        return _single_group([int(i) for i in items])

    groups: list[dict[str, int]] = []
    for item in items:
        if isinstance(item, list):
            groups.append(_single_group([int(i) for i in item]))
        else:
            groups.append(_single_group([int(item)]))
    return groups


def _make_H_gate(H, t, N, tdepth=1):
    """
    Creates the unitary gates for Split JMatrix method.

    Parameter argl: the indicator for which gate to make.
    Precondition: argl is either 'j' or 'H'

    Parameter t: the simulation time.
    Precondition: t is a positive float.

    Parameter N: the number of steps in the algorithm.
    Precondition: N is a positive int.

    Parameter type_gate: the type of gate to make. 0 signifies cavity, anything
    else is an emitter.
    Precondition: type_gate is a positive int.

    Parameter emitter: the emitter index when applicable. Starts from 0.
    Precondition: emitter is an int between 0 and emitters-1 inclusive.

    Parameter tdepth: the Trotterization depth.
    Precondition: tdepth is a positive int.
    """

    return UnitaryGate(scipy.linalg.expm(-1j * H * t / (N * tdepth)))


def _make_J_gate(L, t, N):
    """
    Creates the J gate for Split JMatrix method.
    """
    L = np.asarray(L)
    size = L.shape[0]
    gate = np.block(
        [[np.zeros((size, size)), L.conjugate().T], [L, np.zeros((size, size))]]
    )
    return UnitaryGate(scipy.linalg.expm(-1j * gate * np.sqrt(t / N)))


def _split_jmatrix(
    H: List[LocalHamiltonian],
    Lindblads: List[LocalOperator],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    trotter_depth: int = 1,
):
    Hgates = [_make_H_gate(H_i.matrix, t, num_steps, trotter_depth) for H_i in H]
    Jgates = [_make_J_gate(L_i.matrix, t, num_steps) for L_i in Lindblads]
    ancilla = QuantumRegister(1)
    body = QuantumRegister(num_qubits)
    circ = QuantumCircuit(ancilla, body)

    psi0 = initial_state.to_numpy()

    circ.initialize(psi0, list(reversed(body)))
    circ.barrier()
    for i in range(num_steps):
        # Notebook split-J step: (1) all J (one per Lindblad), (2) all H in list order
        circ.reset(ancilla[0])
        if i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for gate, L_i in zip(Jgates, Lindblads):
            circ.append(gate, reversed([ancilla[0]] + [body[j] for j in L_i.sites]))
            circ.reset(ancilla[0])
        circ.barrier()
        for gate, H_i in zip(Hgates, H):
            circ.append(gate, reversed([body[j] for j in H_i.sites]))

    circ.barrier()

    circ.measure_all()
    backend = AerSimulator()
    compiled = transpile(circ, backend)
    job = backend.run(compiled, shots=10000)
    result = job.result()
    return result.get_counts()


def _population_one(counts: dict[str, int]) -> float:
    """Return the empirical probability of measuring '1'."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return counts.get("1", 0) / total


def _cavity_population(counts: dict[str, int]) -> float:
    """
    Cavity population reducer for two-bit cavity readout.

    Uses notebook convention:
      population = (3*N("11") + 2*N("10") + 1*N("01")) / shots
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return (
        3 * counts.get("11", 0) + 2 * counts.get("10", 0) + counts.get("01", 0)
    ) / total


class SplitJMatrixSimulator(Simulator):
    def __init__(
        self,
        hamiltonians: List[LocalHamiltonian],
        lindblads: List[LocalOperator],
        initial_state: State,
        num_qubits: int,
        total_time: float,
        time_steps: int,
        num_steps: int,
        trotter_depth: int = 1,
        measurement_groups: list[int | list[int]] | None = None,
        reducers: list[Callable[[dict[str, int]], float]] | None = None,
    ):
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits,
            total_time,
            time_steps,
            "split_jmatrix_simulator",
        )
        for L in self.lindblads:
            if not isinstance(L, LocalOperator):
                raise TypeError(
                    "SplitJMatrixSimulator `lindblads` must be LocalOperator (with "
                    f"`sites` on the register); got {type(L).__name__}."
                )
        self.num_steps = num_steps
        self.trotter_depth = trotter_depth
        if measurement_groups is None:
            measurement_groups = list(range(self.num_qubits))
        self.measurement_groups = measurement_groups

        if reducers is None:
            reducers = [_population_one for _ in self.measurement_groups]
        if len(reducers) != len(self.measurement_groups):
            raise ValueError(
                "reducers and measurement_groups must have the same length"
            )
        self.reducers = reducers

    def simulate(self):
        results = [[] for _ in range(len(self.measurement_groups))]
        for t in self.tlist:
            print(f"Working on time step {round(t, 3)}")
            counts = _split_jmatrix(
                self.hamiltonians,
                self.lindblads,
                self.initial_state,
                self.num_qubits,
                t,
                self.num_steps,
                self.trotter_depth,
            )
            counts = flip_dict(counts)
            traced = _trace_qubits(counts, self.measurement_groups)
            if isinstance(traced, dict):
                traced = [traced]
            for j, reducer in enumerate(self.reducers):
                results[j].append(float(reducer(traced[j])))
        self.results = results
        return results
