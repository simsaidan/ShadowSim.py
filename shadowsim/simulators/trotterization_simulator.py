"""Closed-system Trotterization simulator."""

from collections.abc import Sequence
from typing import Any, Callable, List, Literal, cast

import scipy

from shadowsim.backends.circuit import CircuitBackend, backend_samples, backend_shots
from shadowsim.backends.program import Barrier, Operation, Prepare, Program, Unitary
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator, _Matrix
from shadowsim.core.state import State
from shadowsim.simulators._time_points import TimeCall
from shadowsim.simulators.product_formula_simulator import (
    ProductFormulaSimulator,
    _check_order,
    _default_circuit_backend,
    _measure_all,
    _rotate_to_basis,
)

ProgressCallback = Callable[[int, int], None]


def _local_evolution(h_matrix: _Matrix, dt: float) -> _Matrix:
    """Return the local unitary exp(-i H dt)."""
    return scipy.linalg.expm(-1j * h_matrix * dt)


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
) -> Program:
    """Return one closed-system product-formula program, without measurement.

    ``order=1`` is the first-order product. ``order=2`` is one Strang step per slice.
    ``trotter_depth`` is the number of slices in this time sample, for both orders.
    Each qubit is rotated so a following Z measurement reads its letter of
    ``basis``. ``None`` measures every qubit in Z. Qubit 0 is the least significant
    bit of each matrix.
    """
    if num_steps <= 0:
        raise ValueError("num_steps must be a positive integer")
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")
    _check_order(order)

    delta = t / (num_steps * trotter_depth)
    slice_gates = _trotter_slice_unitaries(hamiltonians, delta, order)
    qubits = tuple(range(num_qubits))
    operations: list[Operation] = [
        Prepare(initial_state.to_numpy(), tuple(reversed(qubits))),
        Barrier(qubits),
    ]

    for i in range(num_steps):
        if verbose and i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for _ in range(trotter_depth):
            for matrix, sites in slice_gates:
                operations.append(Unitary(matrix, tuple(reversed(sites))))

    operations.append(Barrier(qubits))
    operations.extend(_rotate_to_basis(basis, num_qubits))
    return Program(num_qubits, 0, operations)


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

    ``circuit_backend`` executes the program. Omitting it uses Aer.
    ``order=1`` is the first-order product. ``order=2`` is one Strang step per slice.
    ``trotter_depth`` is the number of slices in this time sample, for both orders.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    if seed is not None and not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    program = _trotter_circuit(
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
    measured = Program(num_qubits, num_qubits, (*program.operations, *_measure_all(num_qubits)))
    counts_backend = circuit_backend if circuit_backend is not None else _default_circuit_backend()
    return counts_backend.run_counts(measured, shots=shots, seed=seed)


class TrotterizationSimulator(ProductFormulaSimulator):
    """Simulate closed-system dynamics with a Trotter product formula.

    ``closed_system`` is true, so Lindblad operators are rejected.
    Counts come from ``circuit_backend`` when that backend stores ``shots``.
    Omitting it uses Aer. Before the measurement, each
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
        self._configure_run(
            num_steps=num_steps,
            trotter_depth=trotter_depth,
            order=order,
            verbose=verbose,
            seed=seed,
            progress=progress,
            workers=workers,
            circuit_backend=circuit_backend,
            basis=basis,
        )

    def _time_point_call(self, t: float, _index: int) -> TimeCall:
        """Return the closed-system counts call for time ``t``."""
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        return (
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

    def metrics_circuit(self) -> Program:
        """Return the program executed at the final time.

        A sampling backend includes the computational-basis measurement.
        """
        program = _trotter_circuit(
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
        if not backend_samples(self.circuit_backend):
            return program
        return Program(program.num_qubits, program.num_qubits, (*program.operations, *_measure_all(program.num_qubits)))
