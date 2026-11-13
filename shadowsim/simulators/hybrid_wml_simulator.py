"""Hybrid wave-matrix Lindbladization simulator."""

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

import numpy as np
import scipy.linalg

from shadowsim.backends.circuit import CircuitBackend, backend_shots
from shadowsim.backends.program import Barrier, Measure, Operation, Prepare, Program, Reset, Unitary
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.simulators._time_points import TimeCall
from shadowsim.simulators.product_formula_simulator import (
    ProductFormulaSimulator,
    _default_circuit_backend,
    _rotate_to_basis,
)

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
    operations: list[Operation],
    num_qubits: int,
    program_width: int,
    term: _ProgramTerm,
    matrix: np.ndarray,
) -> None:
    """Load ``term`` onto the program register, swap it in, and trace it out.

    The program register starts at qubit ``1 + num_qubits``. Every qubit of that
    register is reset, including ones this term does not use.
    """
    width = len(term.sites)
    program_qubits = [1 + num_qubits + index for index in range(width)]
    operations.append(Prepare(np.array(term.state, copy=True), tuple(reversed(program_qubits))))
    system_qubits = [1 + site for site in term.sites]
    operations.append(Unitary(matrix, tuple(reversed([*system_qubits, *program_qubits]))))
    for index in range(program_width):
        operations.append(Reset(1 + num_qubits + index))


def _apply_jump_step(operations: list[Operation], term: _JumpTerm, matrix: np.ndarray) -> None:
    """Apply one J-gate on the ancilla plus ``term`` and trace the ancilla out."""
    operations.append(Reset(0))
    indexes = (0, *[1 + site for site in term.sites])
    operations.append(Unitary(matrix, tuple(reversed(indexes))))
    operations.append(Reset(0))


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
) -> Program:
    """Return one hybrid WML program for time ``t``, including the measurement.

    Each of the ``num_steps`` samples one spectral Hamiltonian term or one
    Lindblad. A Hamiltonian term is prepared on the program register and coupled
    with ``exp(-i sgn(λ) SWAP Δ)``, where ``Δ = c t / num_steps``. A Lindblad
    ``L`` is applied as ``exp(-i J_L sqrt(τ))`` with
    ``τ = c t / (num_steps ||L||_F^2)``, so the expected accumulated jump time is
    ``t``. The ancilla and program register are not measured. Qubit 0 is the
    ancilla, and system qubit ``i`` is qubit ``i + 1``.

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
        _jump_unitary(jump.matrix, math.sqrt(prepared.c * t / (num_steps * jump.weight))) for jump in prepared.jumps
    ]
    swap_gates: dict[tuple[int, float], np.ndarray] = {}
    for term in prepared.program:
        key = (len(term.sites), term.sign)
        if key not in swap_gates:
            swap_gates[key] = scipy.linalg.expm(-1j * term.sign * _swap_matrix(len(term.sites)) * delta)

    steps: list[tuple[_ProgramTerm | _JumpTerm, np.ndarray]] = [
        (program_term, swap_gates[(len(program_term.sites), program_term.sign)]) for program_term in prepared.program
    ]
    steps.extend(zip(prepared.jumps, jump_gates, strict=True))

    body = tuple(range(1, 1 + num_qubits))
    operations: list[Operation] = [
        Prepare(initial_state.to_numpy(), tuple(reversed(body))),
        Barrier(body),
    ]
    sequence_seed = _sequence_seed(seed, time_index)
    choices = np.random.default_rng(sequence_seed).choice(
        len(prepared.weights),
        size=num_steps,
        p=prepared.weights / prepared.c,
    )
    for step, choice in enumerate(choices):
        if verbose and step % 10 == 0:
            print(f"Working on iteration {step} out of {num_steps}")
        chosen, matrix = steps[int(choice)]
        if isinstance(chosen, _ProgramTerm):
            _apply_program_step(operations, num_qubits, prepared.program_width, chosen, matrix)
        else:
            _apply_jump_step(operations, chosen, matrix)
    operations.append(Barrier(body))
    operations.extend(_rotate_to_basis(basis, num_qubits, offset=1))
    operations.extend(Measure(1 + index, index) for index in range(num_qubits))
    return Program(1 + num_qubits + prepared.program_width, num_qubits, operations)


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

    The program is :func:`_hybrid_wml_circuit`. ``circuit_backend`` executes it.
    Omitting that backend uses Aer. Counts use Qiskit
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
    counts_backend = circuit_backend if circuit_backend is not None else _default_circuit_backend()
    return counts_backend.run_counts(circuit, shots=shots, seed=_sequence_seed(seed, time_index))


class HybridWMLSimulator(ProductFormulaSimulator):
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

    Counts come from ``circuit_backend``. Omitting it uses Aer.
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
    sampling_backend_error: str = "Hybrid WML samples a circuit and needs a backend with a shot budget"

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
        if self.total_time < 0.0:
            raise ValueError("total_time must be non-negative")
        self._configure_run(
            num_steps=_positive_int("num_steps", num_steps),
            verbose=verbose,
            seed=seed,
            progress=progress,
            workers=workers,
            circuit_backend=circuit_backend,
            basis=basis,
        )
        _prepare(self.hamiltonians, self.lindblads, self.num_qubits)

    def _time_point_call(self, t: float, index: int) -> TimeCall:
        """Return the hybrid WML counts call for time ``t`` at ``index``."""
        hamiltonians = cast(list[LocalHamiltonian], self.hamiltonians)
        lindblads = cast(list[LocalOperator], self.lindblads)
        return (
            _hybrid_wml,
            (
                hamiltonians,
                lindblads,
                self.initial_state,
                self.num_qubits,
                t,
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

    def _extra_metadata(self) -> dict[str, Any]:
        """Return the Lindblad count stored on the result."""
        return {"lindblad_count": len(self.lindblads)}

    def metrics_circuit(self) -> Program:
        """Return the program executed at the final time, including measurement."""
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
