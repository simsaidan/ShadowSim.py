"""Split JMatrix quantum-inspired simulator."""

from typing import Any, Callable, List, Literal, cast

import numpy as np
import scipy

from shadowsim.backends.circuit import CircuitBackend, backend_shots
from shadowsim.backends.program import Barrier, Operation, Prepare, Program, Reset, Unitary
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import _Matrix
from shadowsim.core.state import State
from shadowsim.simulators._time_points import TimeCall
from shadowsim.simulators.product_formula_simulator import (
    ProductFormulaSimulator,
    _check_order,
    _default_circuit_backend,
    _measure_all,
    _rotate_to_basis,
)
from shadowsim.simulators.trotterization_simulator import _trotter_slice_unitaries

__all__ = ["SplitJMatrixSimulator"]

ProgressCallback = Callable[[int, int], None]


def _make_J_gate(L: _Matrix, t: float, N: int) -> np.ndarray:
    """Create the J gate for Split JMatrix method.

    The ancilla is the more-significant bit of the returned matrix.
    """
    matrix = np.asarray(L)
    size = matrix.shape[0]
    gate = np.block([[np.zeros((size, size)), matrix.conjugate().T], [matrix, np.zeros((size, size))]])
    return scipy.linalg.expm(-1j * gate * np.sqrt(t / N))


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
) -> Program:
    """Return one Split JMatrix program, including the final measurement.

    Each step applies every Lindblad jump once, then ``trotter_depth`` Hamiltonian
    slices. ``order=1`` applies each local term for time
    ``t / (num_steps * trotter_depth)``. ``order=2`` is one Strang step per slice.
    Either order covers coherent time ``t``. Before the measurement, each system
    qubit is rotated into its letter of ``basis`` (``None`` is all ``Z``).
    Qubit 0 is the ancilla, and system qubit ``i`` is qubit ``i + 1``.
    """
    if trotter_depth <= 0:
        raise ValueError("trotter_depth must be a positive integer")
    _check_order(order)
    if H:
        delta = t / (num_steps * trotter_depth)
        h_gates = _trotter_slice_unitaries(H, delta, order)
    else:
        h_gates = []
    j_gates = [_make_J_gate(L_i.matrix, t, num_steps) for L_i in Lindblads]
    width = num_qubits + 1
    qubits = tuple(range(width))
    operations: list[Operation] = [
        Prepare(initial_state.to_numpy(), tuple(reversed(range(1, width)))),
        Barrier(qubits),
    ]
    for i in range(num_steps):
        # Split-J step: every Lindblad jump once, then ``trotter_depth`` Hamiltonian slices.
        operations.append(Reset(0))
        if verbose and i % 10 == 0:
            print(f"Working on iteration {i} out of {num_steps}")
        for gate, L_i in zip(j_gates, Lindblads, strict=True):
            indexes = (0, *[1 + site for site in L_i.sites])
            operations.append(Unitary(gate, tuple(reversed(indexes))))
            operations.append(Reset(0))
        operations.append(Barrier(qubits))
        for _ in range(trotter_depth):
            for matrix, sites in h_gates:
                operations.append(Unitary(matrix, tuple(reversed([1 + site for site in sites]))))

    operations.append(Barrier(qubits))
    operations.extend(_rotate_to_basis(basis, num_qubits, offset=1))
    operations.extend(_measure_all(width))
    return Program(width, width, operations)


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
    it. Omitting that backend uses Aer.
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
    counts_backend = circuit_backend if circuit_backend is not None else _default_circuit_backend()
    return counts_backend.run_counts(circ, shots=shots, seed=seed)


class SplitJMatrixSimulator(ProductFormulaSimulator):
    """Simulate open-system dynamics with the Split JMatrix method.

    Each of the ``num_steps`` applies every Lindblad jump once, then
    ``trotter_depth`` Hamiltonian slices. ``order=1`` (the default) applies each
    local term once per slice of width ``t / (num_steps * trotter_depth)``, in
    list order. ``order=2`` uses one Strang step per slice: half-steps forward,
    a full step on the last term, then half-steps in reverse. Either order
    covers coherent time ``t``.

    Counts come from ``circuit_backend``. Omitting it uses Aer.
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
    sampling_backend_error: str = "Split JMatrix samples an ancilla circuit and needs a backend with a shot budget"
    counts_skip: int = 1

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
        """Return the ancilla-circuit counts call for time ``t``."""
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        lindblads = cast(list[LocalOperator], self.lindblads)
        return (
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

    def _extra_metadata(self) -> dict[str, Any]:
        """Return the Lindblad count stored on the result."""
        return {"lindblad_count": len(self.lindblads)}

    def metrics_circuit(self) -> Program:
        """Return the program executed at the final time, including measurement."""
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
