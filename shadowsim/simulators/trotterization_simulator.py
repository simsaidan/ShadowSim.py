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
from shadowsim.simulators.reducers import QUBIT_EXPECTATIONS
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.utils.flip_dict import flip_dict

ProgressCallback = Callable[[int, int], None]


def _check_order(order: int) -> None:
    """Reject product-formula orders other than 1 or 2."""
    if order not in (1, 2):
        raise ValueError("order must be 1 or 2")


def _local_evolution(h_matrix: _Matrix, dt: float) -> _Matrix:
    """Return the local unitary exp(-i H dt)."""
    return scipy.linalg.expm(-1j * h_matrix * dt)


def _checked_basis(basis: str | None, num_qubits: int) -> str:
    """Return one measurement basis letter per qubit. ``None`` is all ``Z``."""
    if basis is None:
        return "Z" * num_qubits
    if not isinstance(basis, str) or len(basis) != num_qubits or any(letter not in "XYZ" for letter in basis):
        raise ValueError(f"basis must be {num_qubits} letters from X, Y, and Z, one per qubit")
    return basis


def _rotate_to_basis(circuit: QuantumCircuit, register: QuantumRegister, basis: str | None, num_qubits: int) -> None:
    """Rotate each qubit so a following Z measurement reads its ``basis`` letter.

    ``X`` gets a Hadamard. ``Y`` gets ``sdg`` and then a Hadamard. ``Z`` is unchanged.
    """
    for qubit, letter in enumerate(_checked_basis(basis, num_qubits)):
        if letter == "Y":
            circuit.sdg(register[qubit])
        if letter in "XY":
            circuit.h(register[qubit])


def _system_counts(counts: dict[str, int], skip: int = 0) -> dict[str, int]:
    """Return counts with bit ``i`` of each key as system qubit ``i``.

    ``counts`` uses Qiskit keys, where the rightmost bit is circuit qubit 0. The
    first ``skip`` circuit qubits are not system qubits. Their bits are dropped
    and the shots that differ only there are added together.
    """
    system: dict[str, int] = {}
    for bitstring, shot_count in flip_dict(counts).items():
        key = bitstring[skip:]
        system[key] = system.get(key, 0) + shot_count
    return system


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
    basis: str | None = None,
) -> QuantumCircuit:
    """Return one closed-system product-formula circuit, without measurement.

    ``order=1`` is the first-order product. ``order=2`` is one Strang step per slice.
    ``trotter_depth`` is the number of slices in this time sample, for both orders.
    Each qubit is rotated so a following Z measurement reads its letter of
    ``basis``. ``None`` measures every qubit in Z.
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
    _rotate_to_basis(circ, body, basis, num_qubits)
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
    basis: str | None = None,
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
        basis=basis,
    )
    circ.measure_all()
    counts_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
    return counts_backend.run_counts(circ, shots=shots, seed=seed)


class TrotterizationSimulator(Simulator):
    """Simulate closed-system dynamics with a Trotter product formula.

    ``closed_system`` is true, so Lindblad operators are rejected.
    Counts come from ``circuit_backend`` when that backend stores ``shots``.
    Omitting it uses :class:`AerCircuitBackend`. Before the measurement, each
    qubit is rotated into its letter of ``basis`` (default all ``Z``). The result
    keeps one counts dict per time point, where bit ``i`` of a key is qubit ``i``.
    Read them with :meth:`measure`. A backend without a shot budget, such as
    PauliPropagation, returns the expectation of each qubit's ``basis`` letter
    from the same circuit with the measurement removed, and the result has no
    counts. :meth:`measure` reads those with :meth:`Measurement.expectation`
    and :meth:`Measurement.population`. The shot count is that backend's
    ``shots`` attribute when it has one.
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

    closed_system: bool = True

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
        verbose: bool = False,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        workers: int = 1,
        circuit_backend: CircuitBackend | None = None,
        basis: str | None = None,
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
        self.basis = _checked_basis(basis, num_qubits)
        self.progress = progress
        self.workers = workers

    def _point_at(self, t: float) -> tuple[list[float], dict[str, int] | None]:
        """Return the counts at time ``t``, or one Pauli expectation per qubit without shots."""
        if backend_samples(self.circuit_backend):
            raw = _trotter_circuit_counts(
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
                basis=self.basis,
            )
            return [], _system_counts(raw)
        return self._expectation_samples(t), None

    def _expectation_samples(self, t: float) -> list[float]:
        """Return each qubit's ``basis`` expectation at time ``t`` from a backend without shots."""
        circuit = _trotter_circuit(
            cast(list[LocalHamiltonian], self.hamiltonians),
            self.initial_state,
            self.num_qubits,
            t,
            self.num_steps,
            self.trotter_depth,
            order=self.order,
            verbose=self.verbose,
            basis=self.basis,
        )
        qubits = list(range(self.num_qubits))
        values = self.circuit_backend.z_expectations(circuit, qubits, shots=1, seed=self.seed)
        return [float(value) for value in values]

    def _on_parallel_result(self, index: int, raw: dict[str, int]) -> dict[str, int]:
        """Return a finished time point's system counts. Runs in the parent process."""
        if self.verbose:
            print(f"Working on time step {round(self.tlist[index], 3)}")
        return _system_counts(raw)

    def _on_parallel_progress(self, index: int, total: int) -> None:
        """Forward one finished parallel time point to the user and the active job."""
        if self.progress is not None:
            self.progress(index, total)
        self._report_completed_step(total)

    def _simulate_serial(self) -> tuple[list[list[float]], list[dict[str, int]] | None]:
        """Run every time point on this process, in ``tlist`` order."""
        width = 0 if backend_samples(self.circuit_backend) else self.num_qubits
        results: list[list[float]] = [[] for _ in range(width)]
        counts_by_time: list[dict[str, int]] = []
        total = len(self.tlist)
        self._begin_step_progress(total)
        for i, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(i, total)
            if self.verbose:
                print(f"Working on time step {round(t, 3)}")
            samples, counts = self._point_at(t)
            for j, sample in enumerate(samples):
                results[j].append(sample)
            if counts is not None:
                counts_by_time.append(counts)
            self._report_completed_step(total)
        return results, counts_by_time if backend_samples(self.circuit_backend) else None

    def _simulate_parallel(self) -> tuple[list[list[float]], list[dict[str, int]]]:
        """Run one sampled process-pool task per time point and return counts in ``tlist`` order."""
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
                    "basis": self.basis,
                },
            )
            for t in self.tlist
        ]
        counts = cast(
            list[dict[str, int]],
            map_time_points(
                self.workers,
                calls,
                progress=self._on_parallel_progress,
                on_result=self._on_parallel_result,
            ),
        )
        return [], counts

    def metrics_circuit(self) -> QuantumCircuit:
        """Return the circuit executed at the final time.

        A sampling backend includes the computational-basis measurement.
        """
        circuit = _trotter_circuit(
            cast(list[LocalHamiltonian], self.hamiltonians),
            self.initial_state,
            self.num_qubits,
            float(self.tlist[-1]),
            self.num_steps,
            self.trotter_depth,
            order=self.order,
            verbose=False,
            basis=self.basis,
        )
        if backend_samples(self.circuit_backend):
            circuit.measure_all()
        return circuit

    def simulate(self) -> SimulationResult:
        """Evolve the closed system and store the counts, or Pauli expectations without shots."""
        started = perf_counter()
        if self.workers == 1:
            results, counts = self._simulate_serial()
        else:
            results, counts = self._simulate_parallel()
        runtime = perf_counter() - started
        self.results = results
        metadata: dict[str, Any] = {
            "num_steps": self.num_steps,
            "trotter_depth": self.trotter_depth,
            "order": self.order,
            "basis": self.basis,
            "circuit_backend": self.circuit_backend.name,
        }
        if backend_samples(self.circuit_backend):
            metadata["shots"] = backend_shots(self.circuit_backend)
        else:
            metadata["observable_kind"] = QUBIT_EXPECTATIONS
        return self._make_result(results, runtime=runtime, seed=self.seed, counts=counts, **metadata)

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
            f"basis={self.basis!r}, "
            f"verbose={self.verbose!r}, "
            f"{self._shots_field()}"
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
