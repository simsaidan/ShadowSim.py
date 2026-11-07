"""Shared product-formula simulator run loop."""

from collections.abc import Callable
from time import perf_counter
from typing import Any, Literal, cast

from qiskit import QuantumCircuit, QuantumRegister

from shadowsim.backends.aer import AerCircuitBackend
from shadowsim.backends.circuit import CircuitBackend, backend_samples, backend_shots
from shadowsim.simulators._time_points import TimeCall, map_time_points
from shadowsim.simulators.reducers import QUBIT_EXPECTATIONS
from shadowsim.simulators.result import SimulationResult
from shadowsim.simulators.simulator import Simulator
from shadowsim.utils.flip_dict import flip_dict

__all__ = ["ProductFormulaSimulator"]

ProgressCallback = Callable[[int, int], None]


def _check_order(order: int) -> None:
    """Reject product-formula orders other than 1 or 2."""
    if order not in (1, 2):
        raise ValueError("order must be 1 or 2")


def _check_seed(seed: object) -> None:
    """Raise unless ``seed`` is an ``int`` or ``None``.

    Raises:
        TypeError: ``seed`` is a ``bool`` or some other non-integer.
    """
    if isinstance(seed, bool) or (seed is not None and not isinstance(seed, int)):
        raise TypeError("seed must be an int or None")


def _check_workers(workers: object) -> int:
    """Return ``workers`` when it is a positive integer.

    Raises:
        TypeError: ``workers`` is not an ``int``. ``bool`` is rejected.
        ValueError: ``workers`` is less than 1.
    """
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise TypeError("workers must be an int")
    if workers < 1:
        raise ValueError("workers must be a positive integer")
    return workers


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


class ProductFormulaSimulator(Simulator):
    """Check shared run settings and simulate each time point.

    A subclass checks its own operators, calls ``_configure_run``, and implements
    ``_time_point_call`` in its own module. That call is the circuit for one time.
    ``simulate`` runs it at every time in ``tlist``, serially or on a process pool.

    ``requires_sampling_backend`` rejects a backend with no shot budget.
    ``sampling_backend_error`` is the message. ``counts_skip`` is how many leading
    circuit qubits are dropped from each counts key. A backend without a shot
    budget runs in the calling process. A subclass that accepts one implements
    ``_expectation_samples``.
    """

    requires_sampling_backend: bool = False
    sampling_backend_error: str = ""
    counts_skip: int = 0
    _records_product_order: bool = False

    num_steps: int
    trotter_depth: int
    order: Literal[1, 2]
    verbose: bool
    seed: int | None
    circuit_backend: CircuitBackend
    basis: str
    progress: ProgressCallback | None
    workers: int

    def _configure_run(
        self,
        *,
        num_steps: int,
        verbose: bool,
        seed: int | None,
        progress: ProgressCallback | None,
        workers: int,
        circuit_backend: CircuitBackend | None,
        basis: str | None,
        trotter_depth: int | None = None,
        order: Literal[1, 2] | None = None,
    ) -> None:
        """Check and store the shared run settings.

        ``Simulator.__init__`` has already stored ``num_qubits``. ``num_steps`` is
        stored as given; the subclass checks it. Pass ``trotter_depth`` and
        ``order`` together, or omit both.

        Args:
            num_steps: Product steps in one time sample.
            verbose: Print each time point as it runs.
            seed: Shot seed. ``None`` leaves the backend unseeded. ``bool`` is rejected.
            progress: Optional ``(index, total)`` callback.
            workers: Process-pool size. ``1`` runs in this process.
            circuit_backend: Sampling or expectation backend. ``None`` uses Aer.
            basis: Measurement letters, one per qubit. ``None`` is all ``Z``.
            trotter_depth: Slices inside one time sample. Omit it when the subclass
                has no product-formula depth.
            order: Product order ``1`` or ``2``. Omit it with ``trotter_depth``.

        Raises:
            TypeError: ``seed`` or ``workers`` has the wrong type.
            ValueError: ``workers`` or ``trotter_depth`` is not positive, ``order``
                is not 1 or 2, ``basis`` is malformed, the backend shot count is
                invalid, a sampling-only subclass has no shot budget, or a backend
                without a shot budget is paired with ``workers`` greater than 1.
        """
        _check_seed(seed)
        checked_workers = _check_workers(workers)
        if trotter_depth is not None and trotter_depth <= 0:
            raise ValueError("trotter_depth must be a positive integer")
        if order is not None:
            _check_order(order)
        chosen = circuit_backend if circuit_backend is not None else AerCircuitBackend()
        if backend_samples(chosen):
            backend_shots(chosen)
        elif self.requires_sampling_backend:
            raise ValueError(self.sampling_backend_error)
        elif checked_workers != 1:
            raise ValueError("a backend without a shot budget runs in the calling process")
        checked_basis = _checked_basis(basis, self.num_qubits)

        self.num_steps = num_steps
        self.verbose = verbose
        self.seed = seed
        self.progress = progress
        self.workers = checked_workers
        self.circuit_backend = chosen
        self.basis = checked_basis
        self._records_product_order = trotter_depth is not None and order is not None
        if trotter_depth is not None:
            self.trotter_depth = trotter_depth
        if order is not None:
            self.order = order

    def _time_point_call(self, t: float, index: int) -> TimeCall:
        """Return the picklable ``(function, args, kwargs)`` for time ``t``.

        ``index`` is the position of ``t`` in ``tlist``. The function is a
        module-level name in the subclass module, so a test can replace it.

        Raises:
            NotImplementedError: The subclass did not supply a circuit call.
        """
        raise NotImplementedError("subclasses supply the circuit call")  # pragma: no cover

    def _expectation_samples(self, t: float) -> list[float]:
        """Return one Pauli expectation per qubit at time ``t``.

        A sampling backend does not call this.

        Raises:
            NotImplementedError: This simulator reads shot counts.
        """
        raise NotImplementedError("this simulator reads shot counts, not Pauli expectations")  # pragma: no cover

    def _on_parallel_result(self, index: int, raw: dict[str, int]) -> dict[str, int]:
        """Return a finished time point's system counts. Runs in the parent process."""
        if self.verbose:
            print(f"Working on time step {round(float(self.tlist[index]), 3)}")
        return _system_counts(raw, skip=self.counts_skip)

    def _on_parallel_progress(self, index: int, total: int) -> None:
        """Forward one finished parallel time point to the user and the active job."""
        if self.progress is not None:
            self.progress(index, total)
        self._report_completed_step(total)

    def _simulate_serial(self) -> tuple[list[list[float]], list[dict[str, int]] | None]:
        """Run every time point on this process, in ``tlist`` order."""
        sampling = backend_samples(self.circuit_backend)
        width = 0 if sampling else self.num_qubits
        results: list[list[float]] = [[] for _ in range(width)]
        counts_by_time: list[dict[str, int]] = []
        total = len(self.tlist)
        self._begin_step_progress(total)
        for index, t in enumerate(self.tlist):
            if self.progress is not None:
                self.progress(index, total)
            if self.verbose:
                print(f"Working on time step {round(float(t), 3)}")
            moment = float(t)
            if sampling:
                function, args, kwargs = self._time_point_call(moment, index)
                raw = cast(dict[str, int], function(*args, **kwargs))
                counts_by_time.append(_system_counts(raw, skip=self.counts_skip))
            else:
                for qubit, sample in enumerate(self._expectation_samples(moment)):
                    results[qubit].append(sample)
            self._report_completed_step(total)
        return results, counts_by_time if sampling else None

    def _simulate_parallel(self) -> tuple[list[list[float]], list[dict[str, int]]]:
        """Run one sampled process-pool task per time point and return counts in ``tlist`` order."""
        self._begin_step_progress(len(self.tlist))
        calls = [self._time_point_call(float(t), index) for index, t in enumerate(self.tlist)]
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

    def _extra_metadata(self) -> dict[str, Any]:
        """Return subclass metadata. The default adds nothing."""
        return {}

    def _metadata(self) -> dict[str, Any]:
        """Return result metadata for this run."""
        metadata: dict[str, Any] = {"num_steps": self.num_steps}
        if self._records_product_order:
            metadata["trotter_depth"] = self.trotter_depth
            metadata["order"] = self.order
        metadata["basis"] = self.basis
        metadata["circuit_backend"] = self.circuit_backend.name
        if backend_samples(self.circuit_backend):
            metadata["shots"] = backend_shots(self.circuit_backend)
        else:
            metadata["observable_kind"] = QUBIT_EXPECTATIONS
        metadata.update(self._extra_metadata())
        return metadata

    def simulate(self) -> SimulationResult:
        """Run every time point and store counts, or Pauli expectations without shots.

        ``workers`` of 1 runs in this process, in ``tlist`` order. A larger pool
        runs one sampled task per time point. Results stay in ``tlist`` order.

        Returns:
            The stored simulation result.
        """
        started = perf_counter()
        if self.workers == 1:
            results, counts = self._simulate_serial()
        else:
            results, counts = self._simulate_parallel()
        runtime = perf_counter() - started
        self.results = results
        return self._make_result(results, runtime=runtime, seed=self.seed, counts=counts, **self._metadata())

    def _product_formula_fields(self) -> str:
        """Return the ``trotter_depth`` and ``order`` text, or an empty string."""
        if not self._records_product_order:
            return ""
        return f"trotter_depth={self.trotter_depth}, order={self.order}, "

    def _shots_field(self) -> str:
        """Return the shot budget for ``str`` and ``repr``, or an empty string."""
        if not backend_samples(self.circuit_backend):
            return ""
        return f"shots={backend_shots(self.circuit_backend)}, "

    def __str__(self) -> str:
        """Return a short string representation of the simulator."""
        return (
            f"{type(self).__name__}("
            f"num_qubits={self.num_qubits}, "
            f"num_steps={self.num_steps}, "
            f"{self._product_formula_fields()}"
            f"time_steps={self.time_steps}, "
            f"{self._shots_field()}"
            f"seed={self.seed}"
            ")"
        )

    def __repr__(self) -> str:
        """Return a detailed string representation of the simulator."""
        return (
            f"{type(self).__name__}("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}, "
            f"num_steps={self.num_steps}, "
            f"{self._product_formula_fields()}"
            f"basis={self.basis!r}, "
            f"verbose={self.verbose!r}, "
            f"{self._shots_field()}"
            f"seed={self.seed!r}, "
            f"workers={self.workers}, "
            f"progress={self.progress!r}"
            ")"
        )
