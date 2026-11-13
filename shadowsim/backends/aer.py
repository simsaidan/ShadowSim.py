"""Run shot circuits on Qiskit Aer."""

import re
from collections.abc import Sequence

from qiskit import QuantumCircuit, transpile
from qiskit.circuit import ClassicalRegister
from qiskit.transpiler.exceptions import TranspilerError
from qiskit_aer import AerSimulator
from qiskit_aer.backends.backend_utils import BASIS_GATES

from shadowsim.backends._arguments import _qubit_indexes, _require_shots
from shadowsim.backends.circuit import to_qiskit
from shadowsim.backends.program import Program
from shadowsim.utils.flip_dict import flip_dict

# ``store`` is a simulator instruction, not a gate a circuit can be compiled into.
_EXCLUDED_BASIS_GATES = frozenset({"store"})
_BASIS_GATE_NAMES = tuple(name for name in BASIS_GATES["statevector"] if name not in _EXCLUDED_BASIS_GATES)
_IGNORED_TRANSLATION_OPS = frozenset({"measure", "barrier", "reset", "delay", "snapshot"})
_TRANSLATION_OPS = re.compile(r"""\((['"])([A-Za-z0-9_]+)\1,\s*\d+\)""")


class AerCircuitBackend:
    """Run a program on Qiskit Aer and return shot counts.

    The program is translated to a Qiskit circuit and transpiled for
    ``AerSimulator``. A set ``seed`` is passed as ``seed_simulator``.
    ``basis_gates`` is passed the same way when it is set. ``z_expectations``
    and ``x_expectations`` estimate Pauli expectations from those counts.
    ``depth``, ``width``, ``gate_count``, ``t_count``, and ``toffoli_count``
    read that transpiled circuit. A unitary stays one instruction, so ``t``
    and ``ccx`` counts stay zero unless transpilation emits those names.

    Attributes:
        name: ``"aer"``. Stored on simulation result metadata.
        shots: Shot budget passed to each ``run_counts`` call by a simulator.
        basis_gates: Gate names passed to ``AerSimulator``, or ``None`` for
            Aer's own basis.
        BASIS_GATE_NAMES: Gate names ``basis_gates`` may contain.
    """

    BASIS_GATE_NAMES = _BASIS_GATE_NAMES

    def __init__(self, shots: int = 10000, basis_gates: Sequence[str] | None = None) -> None:
        """Store the shot budget and optional compilation basis.

        Args:
            shots: Number of shots for each circuit. Must be a positive integer.
            basis_gates: Gate names ``transpile`` may use. ``None`` keeps Aer's
                own basis. Names are stripped, lowercased, and de-duplicated.
                Each name must be in ``BASIS_GATE_NAMES``.

        Raises:
            ValueError: ``shots`` is not a positive integer, ``basis_gates`` is
                not a sequence of gate names, the sequence is empty, or a name
                is not a gate Aer can compile into.
        """
        self.name = "aer"
        self.shots = _require_shots(shots)
        self.basis_gates = _basis_gates(basis_gates)

    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Translate ``program`` to Qiskit, transpile that for Aer, and return counts.

        Args:
            program: Program to execute.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            Mapping from bitstring to shot count.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        return self._run_counts(to_qiskit(program), shots=shots, seed=seed)

    def z_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Estimate ``⟨Z⟩`` on ``qubits`` from computational-basis shots.

        Args:
            program: Program to execute, before the computational-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            One estimate per entry of ``qubits``, each ``(n0 - n1) / shots``.

        Raises:
            ValueError: An index is outside ``program``, or ``program`` cannot be
                compiled into ``basis_gates``.
        """
        return _expectations(self, program, qubits, shots=shots, seed=seed, basis="z")

    def x_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Estimate ``⟨X⟩`` on ``qubits`` by applying Hadamard and then measuring.

        Args:
            program: Program to execute, before the X-basis measurement.
            qubits: 0-based indexes in ``program``. The result follows this order.
            shots: Number of shots.
            seed: Passed as ``seed_simulator`` when set. Omitted when ``None``.

        Returns:
            One estimate per entry of ``qubits``, each ``(n0 - n1) / shots``.

        Raises:
            ValueError: An index is outside ``program``, or ``program`` cannot be
                compiled into ``basis_gates``.
        """
        return _expectations(self, program, qubits, shots=shots, seed=seed, basis="x")

    def depth(self, program: Program) -> int:
        """Return the depth of ``program`` after transpilation for Aer.

        Args:
            program: Program to measure. It is translated and transpiled for this basis.

        Returns:
            Length of the critical path on the transpiled circuit.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        return int(self._compiled(program).depth())

    def width(self, program: Program) -> int:
        """Return the qubit count of ``program`` after transpilation for Aer.

        Args:
            program: Program to measure. It is translated and transpiled for this basis.

        Returns:
            Number of qubits on the transpiled circuit. Classical bits are not included.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        return int(self._compiled(program).num_qubits)

    def gate_count(self, program: Program) -> int:
        """Return the instruction count of ``program`` after transpilation for Aer.

        Args:
            program: Program to measure. It is translated and transpiled for this basis.

        Returns:
            Total number of instructions on the transpiled circuit, including
            measurements when ``program`` contains them.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        return int(self._compiled(program).size())

    def t_count(self, program: Program) -> int:
        """Return the number of ``t`` gates after transpilation for Aer.

        ``tdg`` is not included. A multi-qubit unitary stays one instruction, so
        a program built only from unitaries reports zero.

        Args:
            program: Program to measure. It is translated and transpiled for this basis.

        Returns:
            Count of instructions named ``t``.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        return int(self._compiled(program).count_ops().get("t", 0))

    def toffoli_count(self, program: Program) -> int:
        """Return the number of ``ccx`` and ``ccz`` gates after transpilation for Aer.

        A multi-qubit unitary stays one instruction, so a program built only
        from unitaries reports zero.

        Args:
            program: Program to measure. It is translated and transpiled for this basis.

        Returns:
            Sum of ``ccx`` and ``ccz`` instructions.

        Raises:
            ValueError: ``program`` cannot be compiled into ``basis_gates``.
        """
        counts = self._compiled(program).count_ops()
        return int(counts.get("ccx", 0)) + int(counts.get("ccz", 0))

    def _simulator(self, seed: int | None) -> AerSimulator:
        """Return an Aer simulator for this basis and, when set, ``seed``."""
        options: dict[str, object] = {}
        if seed is not None:
            options["seed_simulator"] = seed
        if self.basis_gates is not None:
            options["basis_gates"] = list(self.basis_gates)
        return AerSimulator(**options)

    def _run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Transpile ``circuit`` for Aer and return counts."""
        backend = self._simulator(seed)
        compiled = _transpile(circuit, backend, self.basis_gates)
        job = backend.run(compiled, shots=shots)
        return job.result().get_counts()

    def _compiled(self, program: Program) -> QuantumCircuit:
        """Translate ``program`` and transpile it for this backend's basis."""
        return _transpile(to_qiskit(program), self._simulator(None), self.basis_gates)


def _basis_gates(basis_gates: Sequence[str] | None) -> tuple[str, ...] | None:
    """Return ``basis_gates`` as lowercase names, or ``None`` when unset."""
    if basis_gates is None:
        return None
    if isinstance(basis_gates, (str, bytes)) or not isinstance(basis_gates, Sequence):
        raise ValueError("basis_gates must be a sequence of gate names")
    allowed = set(_BASIS_GATE_NAMES)
    chosen: list[str] = []
    seen: set[str] = set()
    for gate in basis_gates:
        if not isinstance(gate, str):
            raise ValueError("basis_gates must be a sequence of gate names")
        name = gate.strip().lower()
        if not name:
            continue
        if name not in allowed:
            raise ValueError(f"Unknown gate {name}.")
        if name in seen:
            continue
        seen.add(name)
        chosen.append(name)
    if not chosen:
        raise ValueError("Enter at least one gate.")
    return tuple(chosen)


def _transpile(circuit: QuantumCircuit, backend: AerSimulator, basis_gates: tuple[str, ...] | None) -> QuantumCircuit:
    """Transpile ``circuit`` for ``backend``, or raise a short basis error."""
    try:
        return transpile(circuit, backend)
    except TranspilerError as exc:
        raise ValueError(_compile_message(basis_gates, exc)) from exc


def _compile_message(basis_gates: tuple[str, ...] | None, exc: TranspilerError) -> str:
    """Return the page-facing reason ``exc`` could not reach ``basis_gates``."""
    found = {match.group(2) for match in _TRANSLATION_OPS.finditer(str(exc))}
    operations = sorted(found - _IGNORED_TRANSLATION_OPS)
    subject = "this circuit" if not operations else _joined(operations)
    target = "Aer's gates" if not basis_gates else _joined(basis_gates)
    return f"Cannot compile {subject} into {target}."


def _joined(names: Sequence[str]) -> str:
    """Return ``names`` as a phrase with a serial comma."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _expectations(
    backend: AerCircuitBackend,
    program: Program,
    qubits: Sequence[int],
    *,
    shots: int,
    seed: int | None,
    basis: str,
) -> list[float]:
    """Measure ``qubits`` in ``basis`` and return one Pauli expectation per index."""
    indexes = _qubit_indexes(qubits, program.num_qubits, register="program")
    if not indexes:
        return []
    measured = to_qiskit(program)
    if basis == "x":
        for index in dict.fromkeys(indexes):
            measured.h(index)
    offset = measured.num_clbits
    measured.add_register(ClassicalRegister(len(indexes)))
    for slot, index in enumerate(indexes):
        measured.measure(index, offset + slot)
    counts = backend._run_counts(measured, shots=shots, seed=seed)
    # Qiskit separates classical registers with a space. Dropping it leaves
    # clbit 0 at the right, which is the order ``flip_dict`` turns into an index.
    flat = {key.replace(" ", ""): count for key, count in counts.items()}
    flipped = flip_dict(flat)
    return [_outcome_difference(flipped, offset + slot) / shots for slot in range(len(indexes))]


def _outcome_difference(counts: dict[str, int], bit: int) -> int:
    """Return ``n0 - n1`` for classical bit ``bit`` in already-flipped counts."""
    difference = 0
    for bitstring, count in counts.items():
        if bitstring[bit] == "0":
            difference += count
        else:
            difference -= count
    return difference
