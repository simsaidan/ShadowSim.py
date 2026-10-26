"""Estimate single-qubit Pauli expectations with PauliPropagation.jl."""

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NoReturn

import numpy as np
from qiskit import QuantumCircuit, qasm2, transpile
from qiskit.circuit import CircuitInstruction

from shadowsim._optional import import_optional

# OpenQASMInterface exists on this revision, not on the package's current main branch.
_QASM_REVISION = 'Pkg.add(url="https://github.com/SparqleSim/PauliPropagation.jl", rev="6e8c1ae")'
_julia_modules: list[Any] = []
# Gates ``OpenQASMInterface.readqasm`` translates. ``u`` covers one qubit, and
# ``cx`` / ``rxx`` / ``rzz`` cover a general two-qubit unitary after transpilation.
_QASM_BASIS = (
    "u",
    "u1",
    "u2",
    "u3",
    "cx",
    "rx",
    "ry",
    "rz",
    "rxx",
    "rzz",
    "h",
    "x",
    "y",
    "z",
    "s",
    "sdg",
    "t",
    "tdg",
    "sx",
    "cz",
    "swap",
    "id",
    "p",
)


class PauliPropagationBackend:
    """Propagate one Pauli observable per requested qubit.

    The circuit is written as OpenQASM 2 and read by
    ``PauliPropagation.OpenQASMInterface.readqasm``. ``z_expectations`` and
    ``x_expectations`` return the expectation of Z or X on ``|0...0>`` after
    that circuit. Shot counts are not available.

    Attributes:
        name: ``"pauli_propagation"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the PauliPropagation backend name."""
        self.name = "pauli_propagation"

    def run_counts(self, circuit: QuantumCircuit, *, shots: int, seed: int | None) -> dict[str, int]:
        """Reject a request for shot counts.

        Args:
            circuit: Unused. PauliPropagation does not sample a circuit.
            shots: Unused.
            seed: Unused.

        Raises:
            NotImplementedError: PauliPropagation does not support shot counts.
        """
        del circuit, shots, seed
        raise NotImplementedError("PauliPropagation does not support shot counts")

    def z_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
        max_weight: float | None = None,
        min_abs_coeff: float = 1e-10,
    ) -> list[float]:
        """Return ``⟨Z⟩`` for each qubit in ``qubits``.

        Args:
            circuit: Circuit to propagate, without measurements or resets.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.
            max_weight: Largest Pauli weight kept during propagation. Omit it to keep every weight.
            min_abs_coeff: Smallest coefficient magnitude kept during propagation.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``circuit``, the Julia package is missing,
                or the circuit cannot be read.
            ImportError: The ``pauli_propagation`` extra is not installed.
        """
        del shots, seed
        return _expectations(circuit, qubits, "Z", max_weight=max_weight, min_abs_coeff=min_abs_coeff)

    def x_expectations(
        self,
        circuit: QuantumCircuit,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
        max_weight: float | None = None,
        min_abs_coeff: float = 1e-10,
    ) -> list[float]:
        """Return ``⟨X⟩`` for each qubit in ``qubits``.

        Args:
            circuit: Circuit to propagate, without measurements or resets.
            qubits: 0-based indexes in ``circuit.qubits``. The result follows this order.
            shots: Unused. The value is not estimated from shots.
            seed: Unused.
            max_weight: Largest Pauli weight kept during propagation. Omit it to keep every weight.
            min_abs_coeff: Smallest coefficient magnitude kept during propagation.

        Returns:
            One expectation per entry of ``qubits``.

        Raises:
            ValueError: An index is outside ``circuit``, the Julia package is missing,
                or the circuit cannot be read.
            ImportError: The ``pauli_propagation`` extra is not installed.
        """
        del shots, seed
        return _expectations(circuit, qubits, "X", max_weight=max_weight, min_abs_coeff=min_abs_coeff)


def _expectations(
    circuit: QuantumCircuit,
    qubits: Sequence[int],
    pauli: Literal["Z", "X"],
    *,
    max_weight: float | None,
    min_abs_coeff: float,
) -> list[float]:
    """Return one propagated expectation for each index in ``qubits``."""
    indexes = _qubit_indexes(circuit, qubits)
    if not indexes:
        return []
    prepared = _importable_circuit(circuit)
    module = _julia_module()
    nqubits, gates, thetas = _read_qasm(module, prepared)
    return [
        _one_expectation(
            module,
            nqubits,
            gates,
            thetas,
            pauli,
            index + 1,
            max_weight=max_weight,
            min_abs_coeff=min_abs_coeff,
        )
        for index in indexes
    ]


def _qubit_indexes(circuit: QuantumCircuit, qubits: Sequence[int]) -> tuple[int, ...]:
    """Return ``qubits`` when every entry is an index in ``circuit``."""
    indexes: list[int] = []
    for qubit in qubits:
        if isinstance(qubit, bool) or not isinstance(qubit, int) or qubit < 0 or qubit >= circuit.num_qubits:
            raise ValueError(f"qubit {qubit!r} is outside a circuit of {circuit.num_qubits} qubits")
        indexes.append(qubit)
    return tuple(indexes)


def _julia_module() -> Any:
    """Import PauliPropagation into a private Julia module and return that module."""
    juliacall = import_optional("juliacall", extra="pauli_propagation")
    if not _julia_modules:
        _julia_modules.append(juliacall.newmodule("ShadowSimPauliPropagation"))
    module = _julia_modules[0]
    try:
        module.seval("import PauliPropagation")
        available = module.seval("isdefined(PauliPropagation, :OpenQASMInterface)")
    except Exception as exc:
        _reraise_julia(exc)
    if not available:
        raise ValueError(
            f"PauliPropagation.OpenQASMInterface is unavailable. Install that revision with: {_QASM_REVISION}"
        )
    return module


def _reraise_julia(exc: BaseException) -> NoReturn:
    """Raise a short page-visible error for a Julia failure."""
    if type(exc).__module__.split(".", 1)[0] != "juliacall":
        raise exc
    first = next((line.strip() for line in str(exc).splitlines() if line.strip()), "PauliPropagation failed")
    if "PauliPropagation" in first and "not found" in first:
        raise ValueError(
            f"PauliPropagation is not installed in the juliacall project. Install that revision with: {_QASM_REVISION}"
        ) from exc
    raise ValueError(first) from exc


def _read_qasm(module: Any, circuit: QuantumCircuit) -> tuple[int, Any, Any]:
    """Write ``circuit`` as OpenQASM 2 and return ``(nqubits, gates, thetas)``."""
    interface = module.PauliPropagation.OpenQASMInterface
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "circuit.qasm"
        path.write_text(qasm2.dumps(circuit), encoding="utf-8")
        try:
            nqubits, gates, thetas = interface.readqasm(str(path))
        except Exception as exc:
            _reraise_julia(exc)
    return int(nqubits), gates, thetas


def _importable_circuit(circuit: QuantumCircuit) -> QuantumCircuit:
    """Return ``circuit`` using only gates the OpenQASM reader accepts.

    An ``initialize`` of a product state becomes one ``u`` gate per qubit. Other
    unitaries are transpiled into the reader's basis.
    """
    prepared = QuantumCircuit(circuit.num_qubits)
    for instruction in circuit.data:
        name = instruction.operation.name
        if name in {"barrier", "id"}:
            continue
        if name == "measure":
            raise ValueError("PauliPropagation cannot run a circuit that measures a qubit")
        if name == "reset":
            raise ValueError("PauliPropagation cannot run a circuit that resets a qubit")
        qargs = [prepared.qubits[circuit.find_bit(qubit).index] for qubit in instruction.qubits]
        if name == "initialize":
            _append_initialize(prepared, instruction, qargs)
            continue
        prepared.append(instruction.operation, qargs)
    decomposed = transpile(prepared, basis_gates=list(_QASM_BASIS), optimization_level=1)
    unknown = sorted({item.operation.name for item in decomposed.data} - set(_QASM_BASIS))
    if unknown:
        raise ValueError(f"PauliPropagation cannot import gate {unknown[0]!r}")
    return decomposed


def _append_initialize(circuit: QuantumCircuit, instruction: CircuitInstruction, qargs: list[Any]) -> None:
    """Prepare a product state on ``qargs`` with one ``u`` gate per qubit.

    ``qargs[0]`` is the least significant bit of the initialize statevector, matching
    Qiskit's ``initialize``.
    """
    amplitudes = np.asarray(instruction.operation.params, dtype=np.complex128)
    kets = _product_kets(amplitudes)
    if kets is None:
        raise ValueError("PauliPropagation can prepare a product of single-qubit states")
    for ket, qubit in zip(kets, qargs, strict=True):
        theta, phi, lam = _u3_from_ket(ket)
        if max(abs(theta), abs(phi), abs(lam)) < 1e-12:
            continue
        circuit.u(theta, phi, lam, qubit)


def _product_kets(amplitudes: np.ndarray) -> list[np.ndarray] | None:
    """Return one ket per qubit when ``amplitudes`` is a product state.

    Qubit 0 is the least significant bit of the statevector index. Returns ``None``
    when the state does not factor across every qubit.
    """
    vector = np.asarray(amplitudes, dtype=np.complex128).reshape(-1)
    if vector.size == 0 or vector.size & (vector.size - 1):
        return None
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return None
    vector = vector / norm
    remaining = vector
    kets: list[np.ndarray] = []
    while remaining.size > 1:
        rest = remaining.size // 2
        matrix = np.empty((2, rest), dtype=np.complex128)
        matrix[0, :] = remaining[0::2]
        matrix[1, :] = remaining[1::2]
        left, singular, right = np.linalg.svd(matrix, full_matrices=False)
        if singular.size > 1 and singular[1] > 1e-8:
            return None
        kets.append(left[:, 0].copy())
        remaining = singular[0] * right[0]
    reconstructed = kets[0]
    for ket in kets[1:]:
        reconstructed = np.kron(ket, reconstructed)
    overlap = complex(np.vdot(reconstructed, vector))
    if abs(abs(overlap) - 1.0) > 1e-6:
        return None
    kets[0] = kets[0] * (overlap / abs(overlap))
    return kets


def _u3_from_ket(ket: np.ndarray) -> tuple[float, float, float]:
    """Return ``u`` angles that prepare ``ket`` from ``|0>``."""
    state = np.asarray(ket, dtype=np.complex128)
    state = state / np.linalg.norm(state)
    if abs(state[0]) > 1e-12:
        state = state * np.exp(-1j * np.angle(state[0]))
    theta = float(2 * np.arctan2(abs(state[1]), state[0].real))
    phi = float(np.angle(state[1])) if abs(state[1]) > 1e-12 else 0.0
    return theta, phi, 0.0


def _one_expectation(
    module: Any,
    nqubits: int,
    gates: Any,
    thetas: Any,
    pauli: Literal["Z", "X"],
    qubit: int,
    *,
    max_weight: float | None,
    min_abs_coeff: float,
) -> float:
    """Return ``overlapwithzero`` of ``pauli`` on the 1-based qubit ``qubit``."""
    propagation = module.PauliPropagation
    observable = propagation.PauliString(nqubits, module.seval("Base.Symbol")(pauli), qubit)
    options: dict[str, float] = {"min_abs_coeff": min_abs_coeff}
    if max_weight is not None:
        options["max_weight"] = max_weight
    try:
        propagated = propagation.propagate(gates, observable, thetas, **options)
        return float(propagation.overlapwithzero(propagated))
    except Exception as exc:
        _reraise_julia(exc)
