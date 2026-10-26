"""Closed-system Trotterization simulator."""

from collections.abc import Sequence
from time import perf_counter
from typing import Any, Callable, List, Literal, cast

import scipy
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.aer import AerCircuitBackend
from shadowsim.backends.circuit import CircuitBackend, backend_samples, backend_shots
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator, _Matrix
from shadowsim.core.state import State
from shadowsim.simulators._time_points import map_time_points
from shadowsim.simulators.reducers import expectation_x, expectation_z, population_one
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
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
        return _single_group([i for i in items if isinstance(i, int)])

    groups: list[dict[str, int]] = []
    for item in items:
        if isinstance(item, list):
            groups.append(_single_group([int(i) for i in item]))
        else:
            groups.append(_single_group([int(item)]))
    return groups


def _check_order(order: int) -> None:
    """Reject product-formula orders other than 1 or 2."""
    if order not in (1, 2):
        raise ValueError("order must be 1 or 2")


def _local_evolution(h_matrix: _Matrix, dt: float) -> _Matrix:
    """Return the local unitary exp(-i H dt)."""
    return scipy.linalg.expm(-1j * h_matrix * dt)


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


def _one_measured_qubit(group: int | list[int]) -> int:
    """Return the single circuit qubit in a measurement group."""
    if isinstance(group, bool):
        raise ValueError("PauliPropagation measures one qubit at a time")
    if isinstance(group, int):
        return group
    if isinstance(group, list) and len(group) == 1 and isinstance(group[0], int) and not isinstance(group[0], bool):
        return group[0]
    raise ValueError("PauliPropagation measures one qubit at a time")


def _hadamards(circuit: QuantumCircuit, register: QuantumRegister, x_qubits: list[int] | None, num_qubits: int) -> None:
    """Rotate ``x_qubits`` into the X basis before measurement."""
    for qubit in _checked_x_qubits(x_qubits, num_qubits):
        circuit.h(register[qubit])


def _trotter_slice_unitaries(
    hamiltonians: Sequence[LocalHamiltonian],
    delta: float,
    order: Literal[1, 2],
) -> list[tuple[_Matrix, list[int]]]:
    """Return one slice of local unitaries in the order they are applied.

    ``delta`` is the slice width. ``order=1`` applies each term for time ``delta``.
    ``order=2`` is a Strang step: half-steps forward, a full step on the last term,
    then half-steps in reverse. The first entry is applied first.
    """
    _check_order(order)
    if order == 1:
        return [(_local_evolution(h_i.matrix, delta), list(h_i.sites)) for h_i in hamiltonians]
    forward = [(_local_evolution(h_i.matrix, delta / 2), list(h_i.sites)) for h_i in hamiltonians[:-1]]
    last = hamiltonians[-1]
    full = (_local_evolution(last.matrix, delta), list(last.sites))
    return [*forward, full, *reversed(forward)]


def _trotter_circuit(
    hamiltonians: List[LocalHamiltonian],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    trotter_depth: int = 1,
    order: Literal[1, 2] = 1,
    verbose: bool = False,
    x_qubits: list[int] | None = None,
) -> QuantumCircuit:
    """Return one closed-system product-formula circuit, without measurement.

    ``order=1`` is the first-order product. ``order=2`` is one Strang step per slice.
    ``trotter_depth`` is the number of slices in this time sample, for both orders.
    Qubits in ``x_qubits`` get a Hadamard so a following Z measurement reads X.
    """
    if num_steps <= 0:
        raise ValueError("num_steps must be a positive integer")
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")
    _check_order(order)

    delta = t / (num_steps * trotter_depth)
    slice_gates = [
        (UnitaryGate(matrix), sites) for matrix, sites in _trotter_slice_unitaries(hamiltonians, delta, order)
    ]
    body = QuantumRegister(num_qubits)
    circ = QuantumCircuit(body)

    psi0 = initial_state.to_numpy()
    circ.initialize(psi0, list(reversed(body)))
    circ.barrier()

    for i in range(num_steps):
        if verbose and i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for _ in range(trotter_depth):
            for gate, sites in slice_gates:
                circ.append(gate, reversed([body[j] for j in sites]))

    circ.barrier()
    _hadamards(circ, body, x_qubits, num_qubits)
    return circ


def _trotter_circuit_counts(
    hamiltonians: List[LocalHamiltonian],
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
    """Run a closed-system product formula and return counts.

    ``circuit_backend`` executes the circuit. Omitting it uses :class:`AerCircuitBackend`.
    ``order=1`` is the first-order product. ``order=2`` is one Strang step per slice.
    ``trotter_depth`` is the number of slices in this time sample, for both orders.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    if seed is not None and not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    circ = _trotter_circuit(
        hamiltonians,
        initial_state,
        num_qubits,
        t,
        num_steps,
        trotter_depth,
        order=order,
        verbose=verbose,
        x_qubits=x_qubits,
    )
    circ.measure_all()
    counts_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
    return counts_backend.run_counts(circ, shots=shots, seed=seed)


class TrotterizationSimulator(Simulator):
    """Simulate closed-system dynamics with a Trotter product formula.

    Counts come from ``circuit_backend`` when that backend stores ``shots``.
    Omitting it uses :class:`AerCircuitBackend`. A backend without a shot budget,
    such as PauliPropagation, returns one Z expectation per measurement group
    from the same circuit with the measurement removed. The shot count is that
    backend's ``shots`` attribute when it has one.
    With ``workers`` greater than 1, that backend is pickled into each worker process.

    ``order=1`` (the default) applies each local term once per slice of width
    ``t / (num_steps * trotter_depth)``, in list order. ``order=2`` uses one Strang
    step per slice: half-steps forward, a full step on the last term, then half-steps
    in reverse. ``trotter_depth`` is how many slices fit in one time sample, for both
    orders.

    Each time point starts from ``initial_state`` and uses the same ``seed``.
    ``workers=1`` (the default) runs those points serially, in ``tlist`` order.
    ``workers`` greater than 1 runs one process-pool task per time point.
    Traces are still returned in ``tlist`` order, and ``progress(index, total)``
    may run in completion order. A job from ``start()`` counts each finished
    time point in ``completed_steps``.
    """

    def __init__(
        self,
        hamiltonians: list[LocalHamiltonian],
        lindblads: Sequence[Operator],
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
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        workers: int = 1,
        circuit_backend: CircuitBackend | None = None,
        x_qubits: list[int] | None = None,
    ) -> None:
        """Initialize a closed-system Trotterization simulator for the given model."""
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits=num_qubits,
            total_time=total_time,
            time_steps=time_steps,
            id="trotterization_simulator",
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
        _check_order(order)
        if seed is not None and not isinstance(seed, int):
            raise TypeError("seed must be an int or None")
        if isinstance(workers, bool) or not isinstance(workers, int):
            raise TypeError("workers must be an int")
        if workers < 1:
            raise ValueError("workers must be a positive integer")

        self.num_steps = num_steps
        self.trotter_depth = trotter_depth
        self.order = order
        self.verbose = verbose
        self.seed = seed
        self.circuit_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
        if backend_samples(self.circuit_backend):
            backend_shots(self.circuit_backend)
        elif workers != 1:
            raise ValueError("a backend without a shot budget runs in the calling process")
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

    def _samples_at(self, t: float) -> list[float]:
        """Return one sample per measurement group at time ``t``."""
        if backend_samples(self.circuit_backend):
            counts = _trotter_circuit_counts(
                cast(list[LocalHamiltonian], self.hamiltonians),
                self.initial_state,
                self.num_qubits,
                t,
                self.num_steps,
                self.trotter_depth,
                order=self.order,
                verbose=self.verbose,
                shots=backend_shots(self.circuit_backend),
                seed=self.seed,
                circuit_backend=self.circuit_backend,
                x_qubits=self.x_qubits,
            )
            return self._reduce_counts(counts)
        return self._expectation_samples(t)

    def _expectation_samples(self, t: float) -> list[float]:
        """Return Pauli expectations for one time point from a backend without shots."""
        for reducer in self.reducers:
            if reducer not in (population_one, expectation_z, expectation_x):
                raise ValueError("PauliPropagation can return Z and X expectations")
        qubits = [_one_measured_qubit(group) for group in self.measurement_groups]
        circuit = _trotter_circuit(
            cast(list[LocalHamiltonian], self.hamiltonians),
            self.initial_state,
            self.num_qubits,
            t,
            self.num_steps,
            self.trotter_depth,
            order=self.order,
            verbose=self.verbose,
            x_qubits=self.x_qubits,
        )
        values = self.circuit_backend.z_expectations(circuit, qubits, shots=1, seed=self.seed)
        return [
            (1.0 - float(value)) / 2.0 if reducer is population_one else float(value)
            for reducer, value in zip(self.reducers, values, strict=True)
        ]

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
            samples = self._samples_at(t)
            for j, sample in enumerate(samples):
                results[j].append(sample)
            self._report_completed_step(total)
        return results

    def _simulate_parallel(self) -> list[list[float]]:
        """Run one process-pool task per time point and assemble ``tlist`` order."""
        self._begin_step_progress(len(self.tlist))
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        calls = [
            (
                _trotter_circuit_counts,
                (
                    hamiltonians,
                    self.initial_state,
                    self.num_qubits,
                    t,
                    self.num_steps,
                    self.trotter_depth,
                ),
                {
                    "order": self.order,
                    "verbose": self.verbose,
                    "shots": backend_shots(self.circuit_backend),
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
        """Evolve the closed system with Trotterization and store reduced traces."""
        started = perf_counter()
        if self.workers == 1:
            results = self._simulate_serial()
        else:
            results = self._simulate_parallel()
        runtime = perf_counter() - started
        self.results = results
        metadata: dict[str, Any] = {
            "num_steps": self.num_steps,
            "trotter_depth": self.trotter_depth,
            "order": self.order,
            "measurement_group_count": len(self.measurement_groups),
            "circuit_backend": self.circuit_backend.name,
        }
        if backend_samples(self.circuit_backend):
            metadata["shots"] = backend_shots(self.circuit_backend)
        return self._make_result(results, runtime=runtime, seed=self.seed, **metadata)

    def _shots_field(self) -> str:
        """Return the shot budget for ``str`` and ``repr``, or an empty string."""
        if not backend_samples(self.circuit_backend):
            return ""
        return f"shots={backend_shots(self.circuit_backend)}, "

    def __str__(self) -> str:
        """Return a short string representation of the simulator."""
        return (
            "TrotterizationSimulator("
            f"num_qubits={self.num_qubits}, "
            f"num_steps={self.num_steps}, "
            f"trotter_depth={self.trotter_depth}, "
            f"order={self.order}, "
            f"time_steps={self.time_steps}, "
            f"{self._shots_field()}"
            f"seed={self.seed}"
            ")"
        )

    def __repr__(self) -> str:
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
            f"order={self.order}, "
            f"measurement_groups={self.measurement_groups!r}, "
            f"verbose={self.verbose!r}, "
            f"{self._shots_field()}"
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
