"""Closed-system Trotterization simulator via Aer product formulas."""

from typing import Callable, List

import scipy
from qiskit import QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit.library import UnitaryGate
from qiskit_aer import AerSimulator

from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.state import State
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.splitjmatrix_simulator import population_one
from shadowsim.utils.flip_dict import flip_dict

ProgressCallback = Callable[[int, int], None]


def _trace_qubits(
    counts: dict[str, int], qubit_indices: int | List[int] | List[int | List[int]]
) -> dict[str, int] | list[dict[str, int]]:
    """Marginalize measurement counts over selected qubits.

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


def _make_h_gate(h_matrix, t: float, num_steps: int, trotter_depth: int = 1):
    """Build a local product-formula unitary for one Hamiltonian term."""
    return UnitaryGate(scipy.linalg.expm(-1j * h_matrix * t / (num_steps * trotter_depth)))


def _trotter_circuit_counts(
    hamiltonians: List[LocalHamiltonian],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    trotter_depth: int = 1,
    verbose: bool = False,
    shots: int = 10000,
    seed: int | None = None,
):
    """Run a closed-system first-order product formula on Aer and return counts."""
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    if seed is not None and not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    if num_steps <= 0:
        raise ValueError("num_steps must be a positive integer")
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")

    h_gates = [_make_h_gate(h_i.matrix, t, num_steps, trotter_depth) for h_i in hamiltonians]
    body = QuantumRegister(num_qubits)
    circ = QuantumCircuit(body)

    psi0 = initial_state.to_numpy()
    circ.initialize(psi0, list(reversed(body)))
    circ.barrier()

    for i in range(num_steps):
        if verbose and i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for _ in range(trotter_depth):
            for gate, h_i in zip(h_gates, hamiltonians):
                circ.append(gate, reversed([body[j] for j in h_i.sites]))

    circ.barrier()
    circ.measure_all()
    backend = AerSimulator(seed_simulator=seed) if seed is not None else AerSimulator()
    compiled = transpile(circ, backend)
    job = backend.run(compiled, shots=shots)
    return job.result().get_counts()


class TrotterizationSimulator(Simulator):
    """Simulate closed-system dynamics with a first-order Trotter product formula via Aer."""

    def __init__(
        self,
        hamiltonians: list[LocalHamiltonian],
        lindblads: list,
        initial_state: State,
        num_qubits: int,
        total_time: float,
        time_steps: int,
        num_steps: int,
        trotter_depth: int = 1,
        measurement_groups: list[int | list[int]] | None = None,
        reducers: list[Callable[[dict[str, int]], float]] | None = None,
        verbose: bool = False,
        shots: int = 10000,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
    ):
        """Initialize a closed-system Trotterization simulator for the given model."""
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits,
            total_time,
            time_steps,
            "trotterization_simulator",
        )
        if self.lindblads:
            raise ValueError("TrotterizationSimulator is closed-system only; lindblads must be empty")
        for h in self.hamiltonians:
            if not isinstance(h, LocalHamiltonian):
                raise TypeError(
                    "TrotterizationSimulator `hamiltonians` must be LocalHamiltonian "
                    f"(with `sites` on the register); got {type(h).__name__}."
                )
        if num_steps <= 0:
            raise ValueError("num_steps must be a positive integer")
        if trotter_depth <= 0:
            raise ValueError("trotter_depth must be a positive integer")
        if shots <= 0:
            raise ValueError("shots must be a positive integer")
        if seed is not None and not isinstance(seed, int):
            raise TypeError("seed must be an int or None")

        self.num_steps = num_steps
        self.trotter_depth = trotter_depth
        self.verbose = verbose
        self.shots = shots
        self.seed = seed
        self.progress = progress
        if measurement_groups is None:
            measurement_groups = list(range(self.num_qubits))
        self.measurement_groups = measurement_groups

        if reducers is None:
            reducers = [population_one for _ in self.measurement_groups]
        if len(reducers) != len(self.measurement_groups):
            raise ValueError("reducers and measurement_groups must have the same length")
        self.reducers = reducers

    def simulate(self):
        """Evolve the closed system with Trotterization and store reduced traces."""
        results = [[] for _ in range(len(self.measurement_groups))]
        total = len(self.tlist)
        for i, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(i, total)
            if self.verbose:
                print(f"Working on time step {round(t, 3)}")
            counts = _trotter_circuit_counts(
                self.hamiltonians,
                self.initial_state,
                self.num_qubits,
                t,
                self.num_steps,
                self.trotter_depth,
                verbose=self.verbose,
                shots=self.shots,
                seed=self.seed,
            )
            counts = flip_dict(counts)
            traced = _trace_qubits(counts, self.measurement_groups)
            if isinstance(traced, dict):
                traced = [traced]
            for j, reducer in enumerate(self.reducers):
                results[j].append(float(reducer(traced[j])))
        self.results = results
        return results

    def __str__(self):
        """Return a short string representation of the simulator."""
        return (
            "TrotterizationSimulator("
            f"num_qubits={self.num_qubits}, "
            f"num_steps={self.num_steps}, "
            f"trotter_depth={self.trotter_depth}, "
            f"time_steps={self.time_steps}, "
            f"shots={self.shots}, "
            f"seed={self.seed}"
            ")"
        )

    def __repr__(self):
        """Return a detailed string representation of the simulator."""
        return (
            "TrotterizationSimulator("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}, "
            f"num_steps={self.num_steps}, "
            f"trotter_depth={self.trotter_depth}, "
            f"measurement_groups={self.measurement_groups!r}, "
            f"verbose={self.verbose!r}, "
            f"shots={self.shots}, "
            f"seed={self.seed!r}, "
            f"progress={self.progress!r}"
            ")"
        )
