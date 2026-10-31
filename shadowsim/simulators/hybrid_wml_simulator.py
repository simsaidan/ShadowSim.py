"""Hybrid wave-matrix Lindbladization simulator."""

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import cast

import numpy as np
import scipy.linalg
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.aer import AerCircuitBackend
from shadowsim.backends.circuit import CircuitBackend, backend_samples, backend_shots
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.simulators._time_points import map_time_points
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.simulators.trotterization_simulator import _checked_basis, _rotate_to_basis, _system_counts

__all__ = ["HybridWMLSimulator"]

ProgressCallback = Callable[[int, int], None]

# Drop Hamiltonian eigenvalues that are numerical zeros relative to this scale.
_EIGENVALUE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class _ProgramTerm:
    """One spectral term ``λ|v⟩⟨v|`` of a local Hamiltonian."""

    sites: tuple[int, ...]
    state: np.ndarray
    sign: float


@dataclass(frozen=True)
class _JumpTerm:
    """One local Lindblad operator and its Frobenius weight ``||L||_F^2``."""

    sites: tuple[int, ...]
    matrix: np.ndarray
    weight: float


@dataclass(frozen=True)
class _Prepared:
    """Sampling weights for one hybrid evolution.

    ``program`` terms come first, then ``jumps``. ``weights`` is that same order.
    ``c`` is their sum. ``program_width`` is the largest Hamiltonian support.
    """

    program: tuple[_ProgramTerm, ...]
    jumps: tuple[_JumpTerm, ...]
    weights: np.ndarray
    c: float
    program_width: int


def _positive_int(name: str, value: object) -> int:
    """Return ``value`` when it is a positive integer.

    Raises:
        TypeError: ``value`` is not an ``int``. ``bool`` is rejected.
        ValueError: ``value`` is less than 1.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _check_seed(seed: object) -> None:
    """Raise unless ``seed`` is an ``int`` or ``None``.

    Raises:
        TypeError: ``seed`` is a ``bool`` or some other non-integer.
    """
    if isinstance(seed, bool) or (seed is not None and not isinstance(seed, int)):
        raise TypeError("seed must be an int or None")


def _sequence_seed(seed: int | None, time_index: int) -> int | None:
    """Return the seed for one time point, or ``None`` when ``seed`` is ``None``.

    The value is a pure function of ``seed`` and ``time_index``, including for a
    negative ``seed``. Serial and parallel runs of the same time point draw the
    same term sequence and the same shots.
    """
    if seed is None:
        return None
    digest = hashlib.sha256(f"{int(seed)}:{time_index}".encode()).digest()
    return int.from_bytes(digest[:4], "little")


def _check_support(operator: LocalOperator, num_qubits: int, label: str) -> None:
    """Raise unless ``operator`` is a qubit operator on this register.

    Raises:
        ValueError: ``local_dim`` is not 2, or a site is outside the register.
    """
    if operator.local_dim != 2:
        raise ValueError(f"{label} must act on qubits; local_dim must be 2, got {operator.local_dim}")
    if any(site < 0 or site >= num_qubits for site in operator.sites):
        raise ValueError(f"{label} sites {list(operator.sites)} must lie in 0..{num_qubits - 1}")


def _program_terms(hamiltonian: LocalHamiltonian) -> list[tuple[_ProgramTerm, float]]:
    """Return nonzero spectral terms of ``hamiltonian`` and their weights ``|λ|``."""
    evals, vectors = np.linalg.eigh(np.asarray(hamiltonian.matrix, dtype=np.complex128))
    scale = max(float(np.max(np.abs(evals))), 1.0)
    cutoff = _EIGENVALUE_TOLERANCE * scale
    terms: list[tuple[_ProgramTerm, float]] = []
    for index, value in enumerate(evals):
        lam = float(np.real(value))
        if abs(lam) <= cutoff:
            continue
        state = np.asarray(vectors[:, index], dtype=np.complex128).copy()
        state /= np.linalg.norm(state)
        sign = 1.0 if lam >= 0.0 else -1.0
        term = _ProgramTerm(tuple(hamiltonian.sites), state, sign)
        terms.append((term, abs(lam)))
    return terms


def _prepare(hamiltonians: Sequence[Hamiltonian], lindblads: Sequence[Operator], num_qubits: int) -> _Prepared:
    """Build the sampling distribution for ``hamiltonians`` and ``lindblads``.

    Raises:
        TypeError: A Hamiltonian is not a ``LocalHamiltonian``, or a Lindblad is
            not a ``LocalOperator``.
        ValueError: An operator is not a qubit operator on the register, or every
            weight is zero.
    """
    program: list[_ProgramTerm] = []
    jumps: list[_JumpTerm] = []
    weights: list[float] = []
    program_width = 0
    for hamiltonian in hamiltonians:
        if not isinstance(hamiltonian, LocalHamiltonian):
            raise TypeError(
                "HybridWMLSimulator `hamiltonians` must be LocalHamiltonian (with "
                f"`sites` on the register); got {type(hamiltonian).__name__}."
            )
        _check_support(hamiltonian, num_qubits, "Hamiltonian")
        for term, weight in _program_terms(hamiltonian):
            program.append(term)
            weights.append(weight)
            program_width = max(program_width, len(term.sites))
    for lindblad in lindblads:
        if not isinstance(lindblad, LocalOperator):
            raise TypeError(
                "HybridWMLSimulator `lindblads` must be LocalOperator (with "
                f"`sites` on the register); got {type(lindblad).__name__}."
            )
        _check_support(lindblad, num_qubits, "Lindblad")
        matrix = np.array(lindblad.matrix, dtype=np.complex128, copy=True)
        weight = float(np.linalg.norm(matrix, ord="fro")) ** 2
        if weight <= 0.0:
            continue
        jumps.append(_JumpTerm(tuple(lindblad.sites), matrix, weight))
        weights.append(weight)
    if not weights:
        raise ValueError("Hybrid WML needs a nonzero Hamiltonian eigenvalue or Lindblad weight")
    weight_array = np.asarray(weights, dtype=np.float64)
    return _Prepared(tuple(program), tuple(jumps), weight_array, float(weight_array.sum()), program_width)


@lru_cache(maxsize=8)
def _swap_matrix(num_qubits: int) -> np.ndarray:
    """Return the swap of two ``num_qubits``-qubit registers.

    The basis is the Kronecker basis used by local operators: the first register
    occupies the more-significant bits. ``|system⟩|program⟩`` is sent to
    ``|program⟩|system⟩``.
    """
    dim = 1 << num_qubits
    swap = np.zeros((dim * dim, dim * dim), dtype=np.complex128)
    for system in range(dim):
        for program in range(dim):
            swap[program * dim + system, system * dim + program] = 1.0
    return swap


def _jump_unitary(lindblad: np.ndarray, angle: float) -> np.ndarray:
    """Return ``exp(-i J angle)`` for the block matrix of ``lindblad``.

    The ancilla is the more-significant bit, matching :func:`shadowsim.simulators.splitjmatrix_simulator._make_J_gate`.
    """
    size = lindblad.shape[0]
    zeros = np.zeros((size, size), dtype=np.complex128)
    block = np.block([[zeros, lindblad.conjugate().T], [lindblad, zeros]])
    return scipy.linalg.expm(-1j * block * angle)


def _apply_program_step(
    circuit: QuantumCircuit,
    body: QuantumRegister,
    prog: QuantumRegister,
    term: _ProgramTerm,
    gate: UnitaryGate,
) -> None:
    """Load ``term`` onto the program register, swap it in, and trace it out."""
    width = len(term.sites)
    program_qubits = [prog[i] for i in range(width)]
    circuit.initialize(np.array(term.state, copy=True), list(reversed(program_qubits)))
    system_qubits = [body[site] for site in term.sites]
    circuit.append(gate, reversed([*system_qubits, *program_qubits]))
    for qubit in prog:
        circuit.reset(qubit)


def _apply_jump_step(
    circuit: QuantumCircuit,
    body: QuantumRegister,
    ancilla: QuantumRegister,
    term: _JumpTerm,
    gate: UnitaryGate,
) -> None:
    """Apply one J-gate on the ancilla plus ``term`` and trace the ancilla out."""
    circuit.reset(ancilla[0])
    circuit.append(gate, reversed([ancilla[0], *[body[site] for site in term.sites]]))
    circuit.reset(ancilla[0])


def _program_applier(
    circuit: QuantumCircuit,
    body: QuantumRegister,
    prog: QuantumRegister,
    term: _ProgramTerm,
    gate: UnitaryGate,
) -> Callable[[], None]:
    """Return a closure that applies one sampled Hamiltonian step."""

    def apply() -> None:
        _apply_program_step(circuit, body, prog, term, gate)

    return apply


def _jump_applier(
    circuit: QuantumCircuit,
    body: QuantumRegister,
    ancilla: QuantumRegister,
    term: _JumpTerm,
    gate: UnitaryGate,
) -> Callable[[], None]:
    """Return a closure that applies one sampled Lindblad step."""

    def apply() -> None:
        _apply_jump_step(circuit, body, ancilla, term, gate)

    return apply


def _hybrid_wml_circuit(
    hamiltonians: Sequence[Hamiltonian],
    lindblads: Sequence[Operator],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    *,
    verbose: bool = False,
    seed: int | None = None,
    time_index: int = 0,
    basis: str | None = None,
) -> QuantumCircuit:
    """Return one hybrid WML circuit for time ``t``, including the measurement.

    Each of the ``num_steps`` samples one spectral Hamiltonian term or one
    Lindblad. A Hamiltonian term is prepared on the program register and coupled
    with ``exp(-i sgn(λ) SWAP Δ)``, where ``Δ = c t / num_steps``. A Lindblad
    ``L`` is applied as ``exp(-i J_L sqrt(τ))`` with
    ``τ = c t / (num_steps ||L||_F^2)``, so the expected accumulated jump time is
    ``t``. The ancilla and program register are not measured. Circuit qubit 0 is
    the ancilla, and system qubit ``i`` is circuit qubit ``i + 1``.

    Raises:
        ValueError: ``num_steps`` is not positive, ``t`` is negative, or every
            sampling weight is zero.
    """
    num_steps = _positive_int("num_steps", num_steps)
    if t < 0.0:
        raise ValueError("t must be non-negative")
    prepared = _prepare(hamiltonians, lindblads, num_qubits)
    delta = prepared.c * t / num_steps
    # tau = c*t / (n*||L||_F^2). Drawn with probability ||L||_F^2/c, the expected time is t.
    jump_gates = [
        UnitaryGate(_jump_unitary(jump.matrix, math.sqrt(prepared.c * t / (num_steps * jump.weight))))
        for jump in prepared.jumps
    ]
    swap_gates: dict[tuple[int, float], UnitaryGate] = {}
    for term in prepared.program:
        key = (len(term.sites), term.sign)
        if key not in swap_gates:
            unitary = scipy.linalg.expm(-1j * term.sign * _swap_matrix(len(term.sites)) * delta)
            swap_gates[key] = UnitaryGate(unitary)

    ancilla = QuantumRegister(1, name="ancilla")
    body = QuantumRegister(num_qubits, name="system")
    classical = ClassicalRegister(num_qubits, name="c")
    appliers: list[Callable[[], None]] = []
    if prepared.program_width:
        prog = QuantumRegister(prepared.program_width, name="program")
        circuit = QuantumCircuit(ancilla, body, prog, classical)
        for term in prepared.program:
            gate = swap_gates[(len(term.sites), term.sign)]
            appliers.append(_program_applier(circuit, body, prog, term, gate))
    else:
        circuit = QuantumCircuit(ancilla, body, classical)
    for jump, gate in zip(prepared.jumps, jump_gates, strict=True):
        appliers.append(_jump_applier(circuit, body, ancilla, jump, gate))

    circuit.initialize(initial_state.to_numpy(), list(reversed(body)))
    circuit.barrier(body)
    sequence_seed = _sequence_seed(seed, time_index)
    choices = np.random.default_rng(sequence_seed).choice(
        len(prepared.weights),
        size=num_steps,
        p=prepared.weights / prepared.c,
    )
    for step, choice in enumerate(choices):
        if verbose and step % 10 == 0:
            print(f"Working on iteration {step} out of {num_steps}")
        appliers[int(choice)]()
    circuit.barrier(body)
    _rotate_to_basis(circuit, body, basis, num_qubits)
    circuit.measure(body, classical)
    return circuit


def _hybrid_wml(
    hamiltonians: Sequence[Hamiltonian],
    lindblads: Sequence[Operator],
    initial_state: State,
    num_qubits: int,
    t: float,
    num_steps: int,
    *,
    verbose: bool = False,
    shots: int = 10000,
    seed: int | None = None,
    time_index: int = 0,
    circuit_backend: CircuitBackend | None = None,
    basis: str | None = None,
) -> dict[str, int]:
    """Run one hybrid WML circuit and return raw counts of the system qubits.

    The circuit is :func:`_hybrid_wml_circuit`. ``circuit_backend`` executes it.
    Omitting that backend uses :class:`AerCircuitBackend`. Counts use Qiskit
    endianness; the simulator flips them so bit ``i`` is system qubit ``i``.

    Raises:
        ValueError: ``shots`` is not a positive integer.
        TypeError: ``seed`` is not an ``int`` or ``None``.
    """
    if isinstance(shots, bool) or not isinstance(shots, int) or shots <= 0:
        raise ValueError("shots must be a positive integer")
    _check_seed(seed)
    circuit = _hybrid_wml_circuit(
        hamiltonians,
        lindblads,
        initial_state,
        num_qubits,
        t,
        num_steps,
        verbose=verbose,
        seed=seed,
        time_index=time_index,
        basis=basis,
    )
    counts_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
    return counts_backend.run_counts(circuit, shots=shots, seed=_sequence_seed(seed, time_index))


class HybridWMLSimulator(Simulator):
    """Simulate open-system dynamics with hybrid wave-matrix Lindbladization.

    Each of the ``num_steps`` samples one term. The weight of a Hamiltonian
    eigenvalue ``λ`` is ``|λ|``, and the weight of a Lindblad ``L`` is
    ``||L||_F^2``. Their sum is ``c``. A sampled eigenvalue prepares its
    eigenvector on a program register and applies ``exp(-i sgn(λ) SWAP Δ)`` on
    that register and the term's qubits, with ``Δ = c t / num_steps``, then
    resets the program register. A sampled Lindblad applies
    ``exp(-i J_L sqrt(τ))`` on one ancilla and the Lindblad's qubits, with
    ``τ = c t / (num_steps ||L||_F^2)``, then resets the ancilla. One seeded
    sequence is frozen into the circuit and reused for every shot.

    Counts come from ``circuit_backend``. Omitting it uses :class:`AerCircuitBackend`.
    The shot count is that backend's ``shots`` attribute. Before the measurement,
    each system qubit is rotated into its letter of ``basis`` (default all ``Z``).
    The ancilla and the program register are not measured. Bit ``i`` of a counts
    key is system qubit ``i``. Read those counts with :meth:`measure`.
    With ``workers`` greater than 1, that backend is pickled into each worker process.

    Each time point starts from ``initial_state``. The term sequence and the shot
    sampler are a pure function of ``seed`` and the time index, so ``workers=1``
    and a larger pool return the same counts. ``workers=1`` (the default) runs
    the points serially, in ``tlist`` order. ``progress(index, total)`` may run
    in completion order when ``workers`` is greater than 1. A job from ``start()``
    counts each finished time point in ``completed_steps``.
    """

    requires_sampling_backend: bool = True

    def __init__(
        self,
        hamiltonians: list[LocalHamiltonian],
        lindblads: list[LocalOperator],
        initial_state: State,
        *,
        num_qubits: int,
        total_time: float,
        time_steps: int,
        num_steps: int,
        verbose: bool = False,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        workers: int = 1,
        circuit_backend: CircuitBackend | None = None,
        basis: str | None = None,
    ) -> None:
        """Initialize a hybrid WML simulator for the given model.

        Raises:
            TypeError: An operator has the wrong type, or ``seed`` or ``workers``
                has the wrong type.
            ValueError: ``workers`` or ``num_steps`` is not positive, ``total_time``
                is negative, ``basis`` is malformed, the backend has no shot budget,
                an operator does not act on the register, or every sampling weight
                is zero.
        """
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits=num_qubits,
            total_time=total_time,
            time_steps=time_steps,
            id="hybrid_wml_simulator",
        )
        _check_seed(seed)
        self.num_steps = _positive_int("num_steps", num_steps)
        self.workers = _positive_int("workers", workers)
        if self.total_time < 0.0:
            raise ValueError("total_time must be non-negative")
        self.verbose = verbose
        self.seed = seed
        self.circuit_backend = circuit_backend if circuit_backend is not None else AerCircuitBackend()
        if not backend_samples(self.circuit_backend):
            raise ValueError("Hybrid WML samples a circuit and needs a backend with a shot budget")
        backend_shots(self.circuit_backend)
        self.basis = _checked_basis(basis, num_qubits)
        self.progress = progress
        _prepare(self.hamiltonians, self.lindblads, self.num_qubits)

    def _on_parallel_result(self, index: int, raw: dict[str, int]) -> dict[str, int]:
        """Return a finished time point's system counts. Runs in the parent process."""
        if self.verbose:
            print(f"Working on time step {round(self.tlist[index], 3)}")
        return _system_counts(raw, skip=0)

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
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        lindblads = cast(list[LocalOperator], self.lindblads)
        for index, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(index, total)
            if self.verbose:
                print(f"Working on time step {round(float(t), 3)}")
            raw = _hybrid_wml(
                hamiltonians,
                lindblads,
                self.initial_state,
                self.num_qubits,
                float(t),
                self.num_steps,
                verbose=self.verbose,
                shots=backend_shots(self.circuit_backend),
                seed=self.seed,
                time_index=index,
                circuit_backend=self.circuit_backend,
                basis=self.basis,
            )
            counts_by_time.append(_system_counts(raw, skip=0))
            self._report_completed_step(total)
        return counts_by_time

    def _simulate_parallel(self) -> list[dict[str, int]]:
        """Run one process-pool task per time point and return counts in ``tlist`` order."""
        self._begin_step_progress(len(self.tlist))
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        lindblads = cast(list[LocalOperator], self.lindblads)
        calls = [
            (
                _hybrid_wml,
                (
                    hamiltonians,
                    lindblads,
                    self.initial_state,
                    self.num_qubits,
                    float(t),
                    self.num_steps,
                ),
                {
                    "verbose": self.verbose,
                    "shots": backend_shots(self.circuit_backend),
                    "seed": self.seed,
                    "time_index": index,
                    "circuit_backend": self.circuit_backend,
                    "basis": self.basis,
                },
            )
            for index, t in enumerate(self.tlist)
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
        return _hybrid_wml_circuit(
            cast(list[LocalHamiltonian], self.hamiltonians),
            cast(list[LocalOperator], self.lindblads),
            self.initial_state,
            self.num_qubits,
            float(self.tlist[-1]),
            self.num_steps,
            verbose=False,
            seed=self.seed,
            time_index=len(self.tlist) - 1,
            basis=self.basis,
        )

    def simulate(self) -> SimulationResult:
        """Evolve the system with hybrid WML and store the counts at each time."""
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
            basis=self.basis,
            lindblad_count=len(self.lindblads),
            circuit_backend=self.circuit_backend.name,
        )

    def __str__(self) -> str:
        """Return a string representation of the HybridWMLSimulator."""
        return (
            "HybridWMLSimulator("
            f"num_qubits={self.num_qubits}, "
            f"num_steps={self.num_steps}, "
            f"time_steps={self.time_steps}, "
            f"shots={backend_shots(self.circuit_backend)}, "
            f"seed={self.seed}"
            ")"
        )

    def __repr__(self) -> str:
        """Return a string representation of the HybridWMLSimulator."""
        return (
            "HybridWMLSimulator("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}, "
            f"num_steps={self.num_steps}, "
            f"basis={self.basis!r}, "
            f"verbose={self.verbose!r}, "
            f"shots={backend_shots(self.circuit_backend)}, "
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
