"""Ising and Tavis–Cummings programs match the historical Qiskit layout.

Each simulator builds a ``Program``. The reference circuit uses the layout those
builders used when they still emitted ``QuantumCircuit``: reversed qubit lists,
``S†`` then a Hadamard for Y, and ``measure_all``'s leading barrier. The program
must equal ``from_qiskit`` of that circuit. Trotterization is closed, so the
Tavis–Cummings case passes its Hamiltonian only.
"""

import math

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("scipy")

import scipy.linalg
from qiskit import QuantumCircuit
from qiskit.circuit.library import UnitaryGate

from shadowsim.backends.circuit import from_qiskit
from shadowsim.backends.program import Program
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.state import State
from shadowsim.models import ising, tavis_cummings
from shadowsim.simulators.hybrid_wml_simulator import (
    _hybrid_wml_circuit,
    _jump_unitary,
    _prepare,
    _ProgramTerm,
    _sequence_seed,
    _swap_matrix,
)
from shadowsim.simulators.product_formula_simulator import _measure_all
from shadowsim.simulators.splitjmatrix_simulator import _make_J_gate, _split_jmatrix_circuit
from shadowsim.simulators.trotterization_simulator import _trotter_circuit, _trotter_slice_unitaries

_TIME = 0.2
_STEPS = 1


def _basis(num_qubits: int) -> str:
    """Return a basis that includes X, Y, and Z when the register is long enough."""
    return ("YXZ" * num_qubits)[:num_qubits]


def _rotate(circuit: QuantumCircuit, basis: str, offset: int) -> None:
    """Append the historical basis rotations. Y is ``sdg`` then ``h``."""
    for index, letter in enumerate(basis):
        qubit = offset + index
        if letter == "Y":
            circuit.sdg(qubit)
        if letter in "XY":
            circuit.h(qubit)


def _measure_every(circuit: QuantumCircuit) -> None:
    """Append the barrier and measurements that ``measure_all`` used to add."""
    circuit.barrier()
    for index in range(circuit.num_qubits):
        circuit.measure(index, index)


def _trotter_reference(
    hamiltonians: list[LocalHamiltonian],
    state: State,
    num_qubits: int,
    basis: str,
    *,
    measure: bool,
) -> QuantumCircuit:
    """Rebuild one closed product-formula circuit in the old Qiskit layout."""
    delta = _TIME / _STEPS
    slices = _trotter_slice_unitaries(hamiltonians, delta, 1)
    circuit = QuantumCircuit(num_qubits, num_qubits if measure else 0)
    circuit.initialize(state.to_numpy(), list(reversed(range(num_qubits))))
    circuit.barrier()
    for matrix, sites in slices:
        circuit.append(UnitaryGate(np.asarray(matrix)), list(reversed(sites)))
    circuit.barrier()
    _rotate(circuit, basis, 0)
    if measure:
        _measure_every(circuit)
    return circuit


def _split_reference(
    hamiltonians: list[LocalHamiltonian],
    lindblads: list[LocalOperator],
    state: State,
    num_qubits: int,
    basis: str,
) -> QuantumCircuit:
    """Rebuild one Split JMatrix circuit. Qubit 0 is the ancilla."""
    h_gates = _trotter_slice_unitaries(hamiltonians, _TIME / _STEPS, 1) if hamiltonians else []
    j_gates = [_make_J_gate(lindblad.matrix, _TIME, _STEPS) for lindblad in lindblads]
    width = num_qubits + 1
    circuit = QuantumCircuit(width, width)
    circuit.initialize(state.to_numpy(), list(reversed(range(1, width))))
    circuit.barrier()
    circuit.reset(0)
    for gate, lindblad in zip(j_gates, lindblads, strict=True):
        indexes = (0, *[1 + site for site in lindblad.sites])
        circuit.append(UnitaryGate(np.asarray(gate)), list(reversed(indexes)))
        circuit.reset(0)
    circuit.barrier()
    for matrix, sites in h_gates:
        targets = [1 + site for site in sites]
        circuit.append(UnitaryGate(np.asarray(matrix)), list(reversed(targets)))
    circuit.barrier()
    _rotate(circuit, basis, 1)
    _measure_every(circuit)
    return circuit


def _hybrid_reference(
    hamiltonians: list[LocalHamiltonian],
    lindblads: list[LocalOperator],
    state: State,
    num_qubits: int,
    basis: str,
    seed: int,
) -> QuantumCircuit:
    """Rebuild one hybrid WML circuit, including its sampled term sequence."""
    prepared = _prepare(hamiltonians, lindblads, num_qubits)
    delta = prepared.c * _TIME / _STEPS
    jump_gates = [
        _jump_unitary(jump.matrix, math.sqrt(prepared.c * _TIME / (_STEPS * jump.weight))) for jump in prepared.jumps
    ]
    swap_gates: dict[tuple[int, float], np.ndarray] = {}
    for term in prepared.program:
        key = (len(term.sites), term.sign)
        if key not in swap_gates:
            swap_gates[key] = _swap_coupling(term.sign, len(term.sites), delta)
    steps: list[tuple[object, np.ndarray]] = [
        (term, swap_gates[(len(term.sites), term.sign)]) for term in prepared.program
    ]
    steps.extend(zip(prepared.jumps, jump_gates, strict=True))
    width = 1 + num_qubits + prepared.program_width
    circuit = QuantumCircuit(width, num_qubits)
    body = list(range(1, 1 + num_qubits))
    circuit.initialize(state.to_numpy(), list(reversed(body)))
    circuit.barrier(body)
    choices = np.random.default_rng(_sequence_seed(seed, 0)).choice(
        len(prepared.weights),
        size=_STEPS,
        p=prepared.weights / prepared.c,
    )
    for choice in choices:
        chosen, matrix = steps[int(choice)]
        if isinstance(chosen, _ProgramTerm):
            program_qubits = [1 + num_qubits + index for index in range(len(chosen.sites))]
            circuit.initialize(np.array(chosen.state, copy=True), list(reversed(program_qubits)))
            system = [1 + site for site in chosen.sites]
            circuit.append(UnitaryGate(np.asarray(matrix)), list(reversed([*system, *program_qubits])))
            for index in range(prepared.program_width):
                circuit.reset(1 + num_qubits + index)
        else:
            circuit.reset(0)
            indexes = (0, *[1 + site for site in chosen.sites])
            circuit.append(UnitaryGate(np.asarray(matrix)), list(reversed(indexes)))
            circuit.reset(0)
    circuit.barrier(body)
    _rotate(circuit, basis, 1)
    for index in range(num_qubits):
        circuit.measure(1 + index, index)
    return circuit


def _swap_coupling(sign: float, width: int, delta: float) -> np.ndarray:
    """Return the swap coupling ``exp(-i sign SWAP delta)``."""
    return scipy.linalg.expm(-1j * sign * _swap_matrix(width) * delta)


def _same(program: Program, circuit: QuantumCircuit) -> None:
    """Require ``program`` to be the recording of ``circuit``."""
    assert program == from_qiskit(circuit)


def test_ising_programs_match_the_qiskit_layout() -> None:
    model = ising(n_qubits=3, J=1.0, h=0.5, field="transverse")
    basis = _basis(model.num_qubits)
    bare = _trotter_circuit(
        model.local_hamiltonians,
        model.psi0,
        model.num_qubits,
        _TIME,
        _STEPS,
        basis=basis,
    )
    measured = Program(model.num_qubits, model.num_qubits, (*bare.operations, *_measure_all(model.num_qubits)))
    _same(bare, _trotter_reference(model.local_hamiltonians, model.psi0, model.num_qubits, basis, measure=False))
    _same(measured, _trotter_reference(model.local_hamiltonians, model.psi0, model.num_qubits, basis, measure=True))
    _same(
        _split_jmatrix_circuit(
            model.local_hamiltonians,
            [],
            model.psi0,
            model.num_qubits,
            _TIME,
            _STEPS,
            basis=basis,
        ),
        _split_reference(model.local_hamiltonians, [], model.psi0, model.num_qubits, basis),
    )
    _same(
        _hybrid_wml_circuit(
            model.local_hamiltonians,
            [],
            model.psi0,
            model.num_qubits,
            _TIME,
            _STEPS,
            seed=3,
            basis=basis,
        ),
        _hybrid_reference(model.local_hamiltonians, [], model.psi0, model.num_qubits, basis, seed=3),
    )


def test_tavis_cummings_programs_match_the_qiskit_layout() -> None:
    model = tavis_cummings()
    basis = _basis(model.num_qubits)
    bare = _trotter_circuit(
        model.local_hamiltonians,
        model.psi0,
        model.num_qubits,
        _TIME,
        _STEPS,
        basis=basis,
    )
    measured = Program(model.num_qubits, model.num_qubits, (*bare.operations, *_measure_all(model.num_qubits)))
    _same(bare, _trotter_reference(model.local_hamiltonians, model.psi0, model.num_qubits, basis, measure=False))
    _same(measured, _trotter_reference(model.local_hamiltonians, model.psi0, model.num_qubits, basis, measure=True))
    _same(
        _split_jmatrix_circuit(
            model.local_hamiltonians,
            model.c_ops_local,
            model.psi0,
            model.num_qubits,
            _TIME,
            _STEPS,
            basis=basis,
        ),
        _split_reference(model.local_hamiltonians, model.c_ops_local, model.psi0, model.num_qubits, basis),
    )
    _same(
        _hybrid_wml_circuit(
            model.local_hamiltonians,
            model.c_ops_local,
            model.psi0,
            model.num_qubits,
            _TIME,
            _STEPS,
            seed=3,
            basis=basis,
        ),
        _hybrid_reference(model.local_hamiltonians, model.c_ops_local, model.psi0, model.num_qubits, basis, seed=3),
    )
