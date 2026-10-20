"""Split JMatrix quantum-inspired simulator."""

from time import perf_counter
from typing import Any, Callable, List, Literal, cast

import numpy as np
import scipy
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.circuit import AerCircuitBackend, CircuitBackend
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import _Matrix
from shadowsim.core.state import State
from shadowsim.simulators._time_points import map_time_points
from shadowsim.simulators.reducers import cavity_population, population_one
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import _check_order, _trotter_slice_unitaries
from shadowsim.utils.flip_dict import flip_dict

__all__ = [
    "SplitJMatrixSimulator",
    "cavity_population",
    "population_one",
]

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
        return _single_group([i for i in items if isinstance(i, int)])

    groups: list[dict[str, int]] = []
    for item in items:
        if isinstance(item, list):
            groups.append(_single_group([int(i) for i in item]))
        else:
            groups.append(_single_group([int(item)]))
    return groups


def _checked_x_qubits(x_qubits: list[int] | None, num_qubits: int) -> list[int]:
    """Return the qubits to rotate into the X basis, without duplicates."""
    if not x_qubits:
        return []
    chosen: list[int] = []
    for qubit in x_qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= num_qubits:
            raise ValueError(f"x_qubits must be indexes from 0 to {num_qubits - 1}")
        if qubit not in chosen:
            chosen.append(qubit)
    return chosen


def _hadamards(circuit: QuantumCircuit, register: QuantumRegister, x_qubits: list[int] | None, num_qubits: int) -> None:
    """Rotate ``x_qubits`` into the X basis before measurement."""
    for qubit in _checked_x_qubits(x_qubits, num_qubits):
        circuit.h(register[qubit])


def _make_J_gate(L: _Matrix, t: float, N: int) -> UnitaryGate:
    """Create the J gate for Split JMatrix method."""
    matrix = np.asarray(L)
    size = matrix.shape[0]
    gate = np.block([[np.zeros((size, size)), matrix.conjugate().T], [matrix, np.zeros((size, size))]])
    return UnitaryGate(scipy.linalg.expm(-1j * gate * np.sqrt(t / N)))


def _split_jmatrix(
    H: List[LocalHamiltonian],
    Lindblads: List[LocalOperator],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    trotter_depth: int = 1,
    order: Literal[1, 2] = 1,
    verbose: bool = False,
    shots: int = 10000,
    seed: int | None = None,
    circuit_backend: CircuitBackend | None = None,
    x_qubits: list[int] | None = None,
) -> dict[str, Any]:
    """Run one Split JMatrix circuit and return counts.

    Each step applies every Lindblad jump once, then ``trotter_depth`` Hamiltonian
    slices. ``order=1`` applies each local term for time
    ``t / (num_steps * trotter_depth)``. ``order=2`` is one Strang step per slice.
    Either order covers coherent time ``t``.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    if seed is not None and not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")
    _check_order(order)
    if H:
        delta = t / (num_steps * trotter_depth)
        h_gates = [(UnitaryGate(matrix), sites) for matrix, sites in _trotter_slice_unitaries(H, delta, order)]
    else:
        h_gates = []
    Jgates = [_make_J_gate(L_i.matrix, t, num_steps) for L_i in Lindblads]
    ancilla = QuantumRegister(1)
    body = QuantumRegister(num_qubits)
    circ = QuantumCircuit(ancilla, body)

    psi0 = initial_state.to_numpy()

    circ.initialize(psi0, list(reversed(body)))
    circ.barrier()
    for i in range(num_steps):
        # Split-J step: every Lindblad jump once, then ``trotter_depth`` Hamiltonian slices.
        circ.reset(ancilla[0])
        if verbose and i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for gate, L_i in zip(Jgates, Lindblads):
            circ.append(gate, reversed([ancilla[0]] + [body[j] for j in L_i.sites]))
            circ.reset(ancilla[0])
        circ.barrier()
        for _ in range(trotter_depth):
            for gate, sites in h_gates:
                circ.append(gate, reversed([body[j] for j in sites]))

    circ.barrier()
    _hadamards(circ, body, x_qubits, num_qubits)
    circ.measure_all()
    counts_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
    return counts_backend.run_counts(circ, shots=shots, seed=seed)


class SplitJMatrixSimulator(Simulator):
    """Simulate open-system dynamics with the Split JMatrix method.

    Each of the ``num_steps`` applies every Lindblad jump once, then
    ``trotter_depth`` Hamiltonian slices. ``order=1`` (the default) applies each
    local term once per slice of width ``t / (num_steps * trotter_depth)``, in
    list order. ``order=2`` uses one Strang step per slice: half-steps forward,
    a full step on the last term, then half-steps in reverse. Either order
    covers coherent time ``t``.

    Counts come from ``circuit_backend``. Omitting it uses :class:`AerCircuitBackend`.
    With ``workers`` greater than 1, that backend is pickled into each worker process.

    Each time point starts from ``initial_state`` and uses the same ``seed``.
    ``workers=1`` (the default) runs those points serially, in ``tlist`` order.
    ``workers`` greater than 1 runs one process-pool task per time point.
    Traces are still returned in ``tlist`` order, and ``progress(index, total)``
    may run in completion order. A job from ``start()`` counts each finished
    time point in ``completed_steps``.
    """

    def __init__(
        self,
        hamiltonians: List[LocalHamiltonian],
        lindblads: List[LocalOperator],
        initial_state: State,
        *,
        num_qubits: int,
        total_time: float,
        time_steps: int,
        num_steps: int,
        trotter_depth: int = 1,
        order: Literal[1, 2] = 1,
        measurement_groups: list[int | list[int]] | None = None,
        reducers: list[Callable[[dict[str, int]], float]] | None = None,
        verbose: bool = False,
        shots: int = 10000,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        workers: int = 1,
        circuit_backend: CircuitBackend | None = None,
        x_qubits: list[int] | None = None,
    ) -> None:
        """Initialize a Split JMatrix simulator for the given model."""
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits=num_qubits,
            total_time=total_time,
            time_steps=time_steps,
            id="split_jmatrix_simulator",
        )
        for L in self.lindblads:
            if not isinstance(L, LocalOperator):
                raise TypeError(
                    "SplitJMatrixSimulator `lindblads` must be LocalOperator (with "
                    f"`sites` on the register); got {type(L).__name__}."
                )
        if shots <= 0:
            raise ValueError("shots must be a positive integer")
        if seed is not None and not isinstance(seed, int):
            raise TypeError("seed must be an int or None")
        if isinstance(workers, bool) or not isinstance(workers, int):
            raise TypeError("workers must be an int")
        if workers < 1:
            raise ValueError("workers must be a positive integer")
        if trotter_depth <= 0:
            raise ValueError("trotter_depth must be a positive integer")
        _check_order(order)
        self.num_steps = num_steps
        self.trotter_depth = trotter_depth
        self.order = order
        self.verbose = verbose
        self.shots = shots
        self.seed = seed
        self.circuit_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
        self.x_qubits = _checked_x_qubits(x_qubits, num_qubits)
        self.progress = progress
        self.workers = workers
        if measurement_groups is None:
            measurement_groups = list(range(self.num_qubits))
        self.measurement_groups = measurement_groups

        if reducers is None:
            reducers = [population_one for _ in self.measurement_groups]
        if len(reducers) != len(self.measurement_groups):
            raise ValueError("reducers and measurement_groups must have the same length")
        self.reducers = reducers

    def _reduce_counts(self, counts: dict[str, Any]) -> list[float]:
        """Reduce one time point's counts to one sample per measurement group."""
        traced = _trace_qubits(flip_dict(counts), self.measurement_groups)
        if isinstance(traced, dict):
            groups = [traced]
        else:
            groups = traced
        return [float(reducer(groups[j])) for j, reducer in enumerate(self.reducers)]

    def _on_parallel_result(self, index: int, counts: dict[str, Any]) -> list[float]:
        """Reduce a finished time point. Runs in the parent process."""
        if self.verbose:
            print(f"Working on time step {round(self.tlist[index], 3)}")
        return self._reduce_counts(counts)

    def _on_parallel_progress(self, index: int, total: int) -> None:
        """Forward one finished parallel time point to the user and the active job."""
        if self.progress is not None:
            self.progress(index, total)
        self._report_completed_step(total)

    def _simulate_serial(self) -> list[list[float]]:
        """Run every time point on this process, in ``tlist`` order."""
        results: list[list[float]] = [[] for _ in range(len(self.measurement_groups))]
        total = len(self.tlist)
        self._begin_step_progress(total)
        for i, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(i, total)
            if self.verbose:
                print(f"Working on time step {round(t, 3)}")
            counts = _split_jmatrix(
                cast(list[LocalHamiltonian], self.hamiltonians),
                cast(list[LocalOperator], self.lindblads),
                self.initial_state,
                self.num_qubits,
                t,
                self.num_steps,
                self.trotter_depth,
                order=self.order,
                verbose=self.verbose,
                shots=self.shots,
                seed=self.seed,
                circuit_backend=self.circuit_backend,
                x_qubits=self.x_qubits,
            )
            for j, sample in enumerate(self._reduce_counts(counts)):
                results[j].append(sample)
            self._report_completed_step(total)
        return results

    def _simulate_parallel(self) -> list[list[float]]:
        """Run one process-pool task per time point and assemble ``tlist`` order."""
        self._begin_step_progress(len(self.tlist))
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        lindblads = cast(list[LocalOperator], self.lindblads)
        calls = [
            (
                _split_jmatrix,
                (
                    hamiltonians,
                    lindblads,
                    self.initial_state,
                    self.num_qubits,
                    t,
                    self.num_steps,
                    self.trotter_depth,
                ),
                {
                    "order": self.order,
                    "verbose": self.verbose,
                    "shots": self.shots,
                    # Same seed the serial loop passes for this circuit.
                    "seed": self.seed,
                    "circuit_backend": self.circuit_backend,
                    "x_qubits": self.x_qubits,
                },
            )
            for t in self.tlist
        ]
        samples_by_time = cast(
            list[list[float]],
            map_time_points(
                self.workers,
                calls,
                progress=self._on_parallel_progress,
                on_result=self._on_parallel_result,
            ),
        )
        width = len(self.measurement_groups)
        return [[samples[j] for samples in samples_by_time] for j in range(width)]

    def simulate(self) -> SimulationResult:
        """Evolve the system with Split JMatrix and store reduced traces."""
        started = perf_counter()
        if self.workers == 1:
            results = self._simulate_serial()
        else:
            results = self._simulate_parallel()
        runtime = perf_counter() - started
        self.results = results
        return self._make_result(
            results,
            runtime=runtime,
            seed=self.seed,
            shots=self.shots,
            num_steps=self.num_steps,
            trotter_depth=self.trotter_depth,
            order=self.order,
            measurement_group_count=len(self.measurement_groups),
            lindblad_count=len(self.lindblads),
            circuit_backend=self.circuit_backend.name,
        )

    def __str__(self) -> str:
        """Return a string representation of the SplitJMatrixSimulator."""
        return (
            "SplitJMatrixSimulator("
            f"num_qubits={self.num_qubits}, "
            f"num_steps={self.num_steps}, "
            f"trotter_depth={self.trotter_depth}, "
            f"order={self.order}, "
            f"time_steps={self.time_steps}, "
            f"shots={self.shots}, "
            f"seed={self.seed}"
            ")"
        )

    def __repr__(self) -> str:
        """Return a string representation of the SplitJMatrixSimulator."""
        return (
            "SplitJMatrixSimulator("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}, "
            f"num_steps={self.num_steps}, "
            f"trotter_depth={self.trotter_depth}, "
            f"order={self.order}, "
            f"measurement_groups={self.measurement_groups!r}, "
            f"verbose={self.verbose!r}, "
            f"shots={self.shots}, "
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
