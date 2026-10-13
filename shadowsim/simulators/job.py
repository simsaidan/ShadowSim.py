"""Background jobs for ``Simulator.start()``."""

import threading
from enum import StrEnum
from typing import TYPE_CHECKING

from shadowsim.simulators.result import SimulationResult

if TYPE_CHECKING:
    from shadowsim.simulators.simulator import Simulator


class SimulationStatus(StrEnum):
    """Lifecycle of a :class:`SimulationJob`."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


_UNFINISHED = frozenset({SimulationStatus.PENDING, SimulationStatus.RUNNING})


class SimulationJob:
    """Handle for a ``simulate()`` call running on a worker thread.

    ``completed_steps`` and ``total_steps`` stay ``None`` until the backend
    reports time points. QuTiP does not report them.

    Attributes:
        status: ``pending``, ``running``, ``succeeded``, or ``failed``.
        completed_steps: Finished time points, or ``None`` if this backend
            does not report them.
        total_steps: Time points this run will report, or ``None``.
    """

    def __init__(self, simulator: "Simulator") -> None:
        """Bind a job to ``simulator`` without starting it."""
        self._simulator = simulator
        self._status = SimulationStatus.PENDING
        self._result: SimulationResult | None = None
        self._error: Exception | None = None
        self._completed_steps: int | None = None
        self._total_steps: int | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def status(self) -> SimulationStatus:
        """Return ``pending``, ``running``, ``succeeded``, or ``failed``."""
        with self._lock:
            return self._status

    @property
    def completed_steps(self) -> int | None:
        """Return how many time points have finished, or ``None``."""
        with self._lock:
            return self._completed_steps

    @property
    def total_steps(self) -> int | None:
        """Return how many time points this run reports, or ``None``."""
        with self._lock:
            return self._total_steps

    def result(self, timeout: float | None = None) -> SimulationResult:
        """Return the simulation result, waiting up to ``timeout`` seconds.

        ``timeout=None`` waits until the job finishes. A finished successful
        job returns its ``SimulationResult``. A failed job raises the
        exception from ``simulate()``.

        Args:
            timeout: Seconds to wait. ``None`` waits until the job finishes.

        Returns:
            The ``SimulationResult`` from ``simulate()``.

        Raises:
            TimeoutError: The job is still pending or running when the wait ends.
            Exception: Whatever ``simulate()`` raised.
        """
        if self.status in _UNFINISHED:
            thread = self._thread
            if thread is not None:
                thread.join(timeout)
        with self._lock:
            if self._status is SimulationStatus.SUCCEEDED:
                result = self._result
                if result is None:
                    raise RuntimeError("simulation succeeded without a result")
                return result
            if self._status is SimulationStatus.FAILED:
                error = self._error
                if error is None:
                    raise RuntimeError("simulation failed without an exception")
                raise error
            raise TimeoutError("simulation is still running")

    def _launch(self) -> None:
        """Start the worker thread."""
        thread = threading.Thread(target=self._run, name="shadowsim-simulation", daemon=False)
        self._thread = thread
        thread.start()

    def _run(self) -> None:
        """Mark the job running and call ``simulate()``."""
        with self._lock:
            self._status = SimulationStatus.RUNNING
        try:
            result = self._simulator.simulate()
        except Exception as exc:
            with self._lock:
                self._error = exc
                self._status = SimulationStatus.FAILED
        else:
            with self._lock:
                self._result = result
                self._status = SimulationStatus.SUCCEEDED

    def _begin_steps(self, total: int) -> None:
        """Record that this run will report ``total`` time points, none finished yet."""
        with self._lock:
            self._completed_steps = 0
            self._total_steps = total

    def _note_completed_step(self, total: int) -> None:
        """Count one finished time point and record ``total``."""
        with self._lock:
            completed = self._completed_steps
            self._completed_steps = 1 if completed is None else completed + 1
            self._total_steps = total
