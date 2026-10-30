"""Split JMatrix quantum-inspired simulator."""

from time import perf_counter
from typing import Any, Callable, List, Literal, cast

import numpy as np
import scipy
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.aer import AerCircuitBackend
from shadowsim.backends.circuit import CircuitBackend, backend_samples, backend_shots
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import _Matrix
from shadowsim.core.state import State
from shadowsim.simulators._time_points import map_time_points
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import (
    _check_order,
    _checked_basis,
    _rotate_to_basis,
    _system_counts,
    _trotter_slice_unitaries,
)

__all__ = ["SplitJMatrixSimulator"]

ProgressCallback = Callable[[int, int], None]


def _make_J_gate(L: _Matrix, t: float, N: int) -> UnitaryGate:
    """Create the J gate for Split JMatrix method."""
    matrix = np.asarray(L)
    size = matrix.shape[0]
    gate = np.block([[np.zeros((size, size)), matrix.conjugate().T], [matrix, np.zeros((size, size))]])
    return UnitaryGate(scipy.linalg.expm(-1j * gate * np.sqrt(t / N)))


def _split_jmatrix_circuit(
    H: List[LocalHamiltonian],
    Lindblads: List[LocalOperator],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    trotter_depth: int = 1,
    order: Literal[1, 2] = 1,
    verbose: bool = False,
    basis: str | None = None,
) -> QuantumCircuit:
    """Return one Split JMatrix circuit, including the final measurement.

    Each step applies every Lindblad jump once, then ``trotter_depth`` Hamiltonian
    slices. ``order=1`` applies each local term for time
    ``t / (num_steps * trotter_depth)``. ``order=2`` is one Strang step per slice.
    Either order covers coherent time ``t``. Before the measurement, each system
    qubit is rotated into its letter of ``basis`` (``None`` is all ``Z``).
    Circuit qubit 0 is the ancilla, and system qubit ``i`` is circuit qubit ``i + 1``.
    """
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")
    _check_order(order)
    if H:
        delta = t / (num_steps * trotter_depth)
        h_gates = [(UnitaryGate(matrix), sites) for matrix, sites in _trotter_slice_unitaries(H, delta, order)]
    else:
        h_gates = []
    j_gates = [_make_J_gate(L_i.matrix, t, num_steps) for L_i in Lindblads]
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
        for gate, L_i in zip(j_gates, Lindblads, strict=True):
            circ.append(gate, reversed([ancilla[0]] + [body[j] for j in L_i.sites]))
            circ.reset(ancilla[0])
        circ.barrier()
        for _ in range(trotter_depth):
            for gate, sites in h_gates:
                circ.append(gate, reversed([body[j] for j in sites]))

    circ.barrier()
    _rotate_to_basis(circ, body, basis, num_qubits)
    circ.measure_all()
    return circ


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
    basis: str | None = None,
) -> dict[str, Any]:
    """Run one Split JMatrix circuit and return counts, including the ancilla bit.

    The circuit is :func:`_split_jmatrix_circuit`. ``circuit_backend`` executes
    it. Omitting that backend uses :class:`AerCircuitBackend`.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    if seed is not None and not isinstance(seed, int):
        raise TypeError("seed must be an int or None")
    circ = _split_jmatrix_circuit(
        H,
        Lindblads,
        initial_state,
        num_qubits,
        t,
        num_steps,
        trotter_depth,
        order=order,
        verbose=verbose,
        basis=basis,
    )
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
    The shot count is that backend's ``shots`` attribute. Before the measurement,
    each system qubit is rotated into its letter of ``basis`` (default all ``Z``).
    The result keeps one counts dict per time point, where bit ``i`` of a key is
    system qubit ``i`` and the ancilla bit is dropped.
    Read those counts with :meth:`measure`.
    With ``workers`` greater than 1, that backend is pickled into each worker process.

    Each time point starts from ``initial_state`` and uses the same ``seed``.
    ``workers=1`` (the default) runs those points serially, in ``tlist`` order.
    ``workers`` greater than 1 runs one process-pool task per time point.
    Traces are still returned in ``tlist`` order, and ``progress(index, total)``
    may run in completion order. A job from ``start()`` counts each finished
    time point in ``completed_steps``.
    """

    requires_sampling_backend: bool = True

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
        verbose: bool = False,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        workers: int = 1,
        circuit_backend: CircuitBackend | None = None,
        basis: str | None = None,
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
        self.seed = seed
        self.circuit_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
        if not backend_samples(self.circuit_backend):
            raise ValueError("Split JMatrix samples an ancilla circuit and needs a backend with a shot budget")
        backend_shots(self.circuit_backend)
        self.basis = _checked_basis(basis, num_qubits)
        self.progress = progress
        self.workers = workers

    def _on_parallel_result(self, index: int, raw: dict[str, int]) -> dict[str, int]:
        """Return a finished time point's counts without the ancilla bit. Runs in the parent process."""
        if self.verbose:
            print(f"Working on time step {round(self.tlist[index], 3)}")
        return _system_counts(raw, skip=1)

    def _on_parallel_progress(self, index: int, total: int) -> None:
        """Forward one finished parallel time point to the user and the active job."""
        if self.progress is not None:
            self.progress(index, total)
        self._report_completed_step(total)

    def _simulate_serial(self) -> list[dict[str, int]]:
        """Run every time point on this process and return counts in ``tlist`` order."""
        counts_by_time: list[dict[str, int]] = []
        total = len(self.tlist)
        self._begin_step_progress(total)
        for i, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(i, total)
            if self.verbose:
                print(f"Working on time step {round(t, 3)}")
            raw = _split_jmatrix(
                cast(list[LocalHamiltonian], self.hamiltonians),
                cast(list[LocalOperator], self.lindblads),
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
            counts_by_time.append(_system_counts(raw, skip=1))
            self._report_completed_step(total)
        return counts_by_time

    def _simulate_parallel(self) -> list[dict[str, int]]:
        """Run one process-pool task per time point and return counts in ``tlist`` order."""
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
                    "shots": backend_shots(self.circuit_backend),
                    # Same seed the serial loop passes for this circuit.
                    "seed": self.seed,
                    "circuit_backend": self.circuit_backend,
                    "basis": self.basis,
                },
            )
            for t in self.tlist
        ]
        return cast(
            list[dict[str, int]],
            map_time_points(
                self.workers,
                calls,
                progress=self._on_parallel_progress,
                on_result=self._on_parallel_result,
            ),
        )

    def metrics_circuit(self) -> QuantumCircuit:
        """Return the circuit executed at the final time, including measurement."""
        return _split_jmatrix_circuit(
            cast(list[LocalHamiltonian], self.hamiltonians),
            cast(list[LocalOperator], self.lindblads),
            self.initial_state,
            self.num_qubits,
            float(self.tlist[-1]),
            self.num_steps,
            self.trotter_depth,
            order=self.order,
            verbose=False,
            basis=self.basis,
        )

    def simulate(self) -> SimulationResult:
        """Evolve the system with Split JMatrix and store the counts at each time."""
        started = perf_counter()
        counts = self._simulate_serial() if self.workers == 1 else self._simulate_parallel()
        runtime = perf_counter() - started
        self.results = []
        return self._make_result(
            [],
            runtime=runtime,
            seed=self.seed,
            counts=counts,
            shots=backend_shots(self.circuit_backend),
            num_steps=self.num_steps,
            trotter_depth=self.trotter_depth,
            order=self.order,
            basis=self.basis,
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
            f"shots={backend_shots(self.circuit_backend)}, "
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
            f"basis={self.basis!r}, "
            f"verbose={self.verbose!r}, "
            f"shots={backend_shots(self.circuit_backend)}, "
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
