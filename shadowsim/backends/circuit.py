"""Shared circuit execution for shot-based simulators."""

from typing import Protocol

from qiskit import QuantumCircuit, transpile
from qiskit.providers import BackendV2
from qiskit_aer import AerSimulator


class CircuitBackend(Protocol):
    """Execute one circuit and return measurement counts.

    Attributes:
        name: Identifier stored on simulation result metadata.
    """

    name: str

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Run ``circuit`` for ``shots`` and return bitstring counts.

        Args:
            circuit: Circuit to execute. Implementations transpile it for their target.
            shots: Number of shots.
            seed: Optional seed. Implementations use it only when the target accepts one.

        Returns:
            Mapping from bitstring to shot count.
        """
        ...


class AerCircuitBackend:
    """Run a circuit on Qiskit Aer and return shot counts.

    A set ``seed`` is passed to ``AerSimulator`` as ``seed_simulator``.

    Attributes:
        name: ``"aer"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the Aer backend name."""
        self.name = "aer"

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Transpile ``circuit`` for Aer, run it, and return counts.

        Args:
            circuit: Circuit to execute.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            Mapping from bitstring to shot count.
        """
        backend = AerSimulator(seed_simulator=seed) if seed is not None else AerSimulator()
        compiled = transpile(circuit, backend)
        job = backend.run(compiled, shots=shots)
        return job.result().get_counts()


class QiskitCircuitBackend:
    """Run a circuit on a caller-supplied Qiskit ``BackendV2``.

    The wrapped backend is the object that receives ``run``. ``seed`` is accepted
    so this class matches :class:`CircuitBackend` and is not passed as ``seed_simulator``.

    Attributes:
        name: Label stored on simulation result metadata.
    """

    def __init__(self, backend: BackendV2, *, name: str = "qiskit") -> None:
        """Wrap ``backend`` under ``name``.

        Args:
            backend: Qiskit backend that will receive ``run``.
            name: Metadata label. Defaults to ``"qiskit"``.
        """
        self._backend = backend
        self.name = name

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Transpile ``circuit`` for the wrapped backend, run it, and return counts.

        Args:
            circuit: Circuit to execute.
            shots: Number of shots.
            seed: Unused. This backend does not pass ``seed_simulator``.

        Returns:
            Mapping from bitstring to shot count.

        Raises:
            TypeError: If the run result has no callable ``get_counts``.
        """
        del seed
        compiled = transpile(circuit, self._backend)
        job = self._backend.run(compiled, shots=shots)
        result = job.result()
        get_counts = getattr(result, "get_counts", None)
        if not callable(get_counts):
            raise TypeError("backend result does not provide get_counts()")
        return get_counts()
