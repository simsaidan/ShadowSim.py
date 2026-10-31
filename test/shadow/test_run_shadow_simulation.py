import importlib

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, OperatorSet, State
from shadowsim.shadow import ShadowSimulationResult, run_shadow_simulation
from shadowsim.shadow.run_shadow_simulation import computational_basis_projectors, pad_h_s

_run_mod = importlib.import_module("shadowsim.shadow.run_shadow_simulation")

X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)
EXPECTED_H_S = np.array([[0, -2j], [2j, 0]], dtype=np.complex128)

# These tests fail validation before any circuit runs, so the backend is never called.
_UNUSED_BACKEND = object()


def _zero() -> State:
    return State(np.array([1.0, 0.0], dtype=np.complex128), 1)


def _numpy_backend():
    pytest.importorskip("qiskit")
    from shadowsim.backends.numpy import NumpyCircuitBackend

    return NumpyCircuitBackend()


class _CountingSamplingBackend:
    """Exact NumPy readings behind a ``shots`` budget, recording the shots each call receives."""

    def __init__(self, shots: int) -> None:
        self.name = "counting"
        self.shots = shots
        self.received: list[int] = []
        self._inner = _numpy_backend()

    def x_expectations(self, circuit, qubits, *, shots, seed):
        self.received.append(shots)
        return self._inner.x_expectations(circuit, qubits, shots=shots, seed=seed)


def _physical_expectations(hamiltonian: np.ndarray, state: State, labels: list[str], times: np.ndarray):
    from scipy.linalg import expm

    psi0 = state.to_numpy()
    curves = []
    for label in labels:
        matrix = Operator(label).matrix
        curve = []
        for t in times:
            psi = expm(-1j * hamiltonian * t) @ psi0
            curve.append(float(np.real(np.vdot(psi, matrix @ psi))))
        curves.append(np.array(curve))
    return curves


@pytest.mark.qiskit
def test_run_shadow_simulation_one_qubit_known_h_s():
    result = run_shadow_simulation(
        Hamiltonian(X),
        OperatorSet([Operator(Z)]),
        _zero(),
        total_time=1.0,
        time_steps=11,
        circuit_backend=_numpy_backend(),
    )

    assert isinstance(result, ShadowSimulationResult)
    assert result.shadow_hamiltonian.basis == ["Y", "Z"]
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)
    assert np.allclose(result.H_S_padded, EXPECTED_H_S)
    assert result.shadow_num_qubits == 1
    assert result.times.shape == (11,)
    assert result.labels == ["Y", "Z"]
    assert len(result.expectations) == 2
    for trace in result.expectations:
        assert trace.shape == (11,)
    assert result.shadow_observable_expectations == []
    assert result.shadow_observable_labels == []


@pytest.mark.qiskit
def test_run_shadow_simulation_returns_signed_expectations():
    """Issue #224: H = X, O = Z, |0⟩ gives ⟨Y⟩ = -sin(2t) and ⟨Z⟩ = cos(2t), not their squares."""
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=2.0,
        time_steps=21,
        circuit_backend=_numpy_backend(),
    )
    t = result.times
    assert result.labels == ["Y", "Z"]
    assert np.allclose(result.expectations[0], -np.sin(2 * t), atol=1e-8)
    assert np.allclose(result.expectations[1], np.cos(2 * t), atol=1e-8)
    assert result.expectations[1].min() < -0.9


@pytest.mark.qiskit
def test_run_shadow_simulation_weighted_shadow_state_matches_physical_evolution():
    """A = 2 here, so the readings must be scaled by √A to match the physical curves."""
    state = State(np.ones(8, dtype=np.complex128) / np.sqrt(8), 3)
    result = run_shadow_simulation(
        [Hamiltonian("XII"), Hamiltonian("IIX")],
        OperatorSet(["XII", "YII", "ZII", "IIX"]),
        state,
        total_time=3.0,
        time_steps=13,
        circuit_backend=_numpy_backend(),
    )
    assert result.shadow_state.A == pytest.approx(2.0)
    hamiltonian = Operator("XII").matrix + Operator("IIX").matrix
    expected = _physical_expectations(hamiltonian, state, result.labels, result.times)
    for curve, reference in zip(result.expectations, expected, strict=True):
        assert np.allclose(curve, reference, atol=1e-8)


@pytest.mark.qiskit
def test_run_shadow_simulation_passes_backend_shot_budget():
    backend = _CountingSamplingBackend(shots=123)
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=1.0,
        time_steps=4,
        circuit_backend=backend,
    )
    assert backend.received == [123] * (2 * 4)
    assert np.allclose(result.expectations[1], np.cos(2 * result.times), atol=1e-8)


@pytest.mark.qiskit
def test_run_shadow_simulation_aer_within_shot_noise():
    pytest.importorskip("qiskit_aer")
    from shadowsim.backends.aer import AerCircuitBackend

    shots = 20000
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=2.0,
        time_steps=11,
        circuit_backend=AerCircuitBackend(shots=shots),
        seed=7,
    )
    t = result.times
    tolerance = 5 / np.sqrt(shots)
    assert np.max(np.abs(result.expectations[0] + np.sin(2 * t))) < tolerance
    assert np.max(np.abs(result.expectations[1] - np.cos(2 * t))) < tolerance


@pytest.mark.qiskit
def test_hadamard_test_circuit_reads_each_component_in_order():
    """Distinct components on a 2-qubit shadow space pin the ancilla and register bit order."""
    psi0 = np.array([0.1, -0.3, 0.5, np.sqrt(1 - 0.35)], dtype=np.complex128)
    backend = _numpy_backend()
    readings = []
    for k in range(4):
        circuit = _run_mod._hadamard_test_circuit(psi0, np.eye(4, dtype=np.complex128), k)
        (reading,) = backend.x_expectations(circuit, [0], shots=1, seed=None)
        readings.append(reading)
    assert np.allclose(readings, psi0.real, atol=1e-12)


@pytest.mark.qiskit
def test_run_shadow_simulation_sparse_labels_path():
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=0.5,
        time_steps=5,
        circuit_backend=_numpy_backend(),
    )
    assert result.shadow_hamiltonian.used_sparse_pauli_path is True
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)
    assert result.shadow_num_qubits == 1


@pytest.mark.qiskit
def test_run_shadow_simulation_accepts_observable_sequence():
    """Sequence observables coerce via `_as_operator_set` (not only OperatorSet)."""
    result = run_shadow_simulation(
        Hamiltonian("X"),
        ["Z"],
        _zero(),
        total_time=0.5,
        time_steps=5,
        circuit_backend=_numpy_backend(),
    )
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)


@pytest.mark.qiskit
def test_run_shadow_simulation_local_hamiltonian_skips_dim_check():
    """LocalHamiltonian terms are skipped in physical-dimension validation."""
    result = run_shadow_simulation(
        [LocalHamiltonian(X, [0])],
        OperatorSet([Operator(Z)]),
        _zero(),
        total_time=0.5,
        time_steps=5,
        num_qubits=1,
        circuit_backend=_numpy_backend(),
    )
    assert result.shadow_hamiltonian.used_sparse_pauli_path is False
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)


@pytest.mark.qiskit
def test_run_shadow_simulation_custom_shadow_observables():
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=2.0,
        time_steps=21,
        shadow_observables=computational_basis_projectors(1),
        circuit_backend=_numpy_backend(),
    )
    t = result.times
    assert result.shadow_observable_labels == ["P_0", "P_1"]
    assert np.allclose(result.shadow_observable_expectations[0], np.sin(2 * t) ** 2, atol=1e-8)
    assert np.allclose(result.shadow_observable_expectations[1], np.cos(2 * t) ** 2, atol=1e-8)
    assert result.labels == ["Y", "Z"]
    assert np.allclose(result.expectations[1], np.cos(2 * t), atol=1e-8)


@pytest.mark.qiskit
def test_run_shadow_simulation_shadow_observables_on_padded_space():
    """A 3-operator closure padded to 4: a non-diagonal M matches direct shadow-state evolution."""
    from scipy.linalg import expm

    shift = np.kron(X, np.eye(2, dtype=np.complex128))
    shadow_observables = OperatorSet([Operator(shift), *computational_basis_projectors(2)])
    result = run_shadow_simulation(
        Hamiltonian("X + Z"),
        OperatorSet(["Y"]),
        State(np.array([1.0, 1j], dtype=np.complex128) / np.sqrt(2), 1),
        total_time=2.0,
        time_steps=9,
        shadow_observables=shadow_observables,
        circuit_backend=_numpy_backend(),
    )
    assert result.basis == ["X", "Y", "Z"]
    assert result.shadow_num_qubits == 2
    assert result.shadow_observable_labels == ["0", "P_00", "P_01", "P_10", "P_11"]

    psi0 = result.shadow_state.to_numpy()
    expected = []
    for t in result.times:
        psi = expm(-1j * result.H_S_padded * t) @ psi0
        expected.append(np.real(np.vdot(psi, shift @ psi)))
    assert np.allclose(result.shadow_observable_expectations[0], expected, atol=1e-8)
    assert np.allclose(result.shadow_observable_expectations[4], 0.0)
    assert np.allclose(sum(result.shadow_observable_expectations[1:]), 1.0, atol=1e-8)


def test_run_shadow_simulation_rejects_empty_hamiltonians():
    with pytest.raises(ValueError, match="shadow simulation: hamiltonians"):
        run_shadow_simulation(
            [],
            OperatorSet([Operator(Z)]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_empty_observables():
    with pytest.raises(ValueError, match="shadow simulation: observables"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_num_qubits_mismatch():
    with pytest.raises(ValueError, match="shadow simulation:.*num_qubits"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([Operator(Z)]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            num_qubits=2,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_negative_num_qubits():
    with pytest.raises(ValueError, match="shadow simulation: num_qubits must be non-negative"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([Operator(Z)]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            num_qubits=-1,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_state_dimension_mismatch():
    class _FakeState:
        def get_num_qubits(self):
            return 1

        @property
        def state(self):
            return np.array([1.0, 0.0, 0.0], dtype=np.complex128)

    with pytest.raises(ValueError, match="shadow simulation: initial_state dimension"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([Operator(Z)]),
            _FakeState(),  # type: ignore[arg-type]
            total_time=0.1,
            time_steps=3,
            num_qubits=1,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_hamiltonian_dimension_mismatch():
    state_2q = State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2)
    with pytest.raises(ValueError, match="shadow simulation: Hamiltonian dimension"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([Operator(np.eye(4, dtype=np.complex128))]),
            state_2q,
            total_time=0.1,
            time_steps=3,
            num_qubits=2,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_observable_dimension_mismatch():
    with pytest.raises(ValueError, match="shadow simulation: observable dimension"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([Operator(np.eye(4, dtype=np.complex128))]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            num_qubits=1,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_empty_shadow_observables():
    with pytest.raises(ValueError, match="shadow simulation: shadow_observables must be non-empty"):
        run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            shadow_observables=OperatorSet([]),
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_shadow_observables_dimension_mismatch():
    bad = OperatorSet([Operator(np.eye(4, dtype=np.complex128))])
    with pytest.raises(ValueError, match="shadow simulation: shadow_observables dimension"):
        run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            shadow_observables=bad,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_shadow_state_qubit_mismatch(monkeypatch):
    class _BadShadowState:
        def __init__(self, *_args, **_kwargs):
            self.state = np.array([1.0, 0.0], dtype=np.complex128)

        def get_num_qubits(self):
            return 99

    monkeypatch.setattr(_run_mod, "ShadowState", _BadShadowState)
    with pytest.raises(ValueError, match="padded shadow state qubit count"):
        run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_run_shadow_simulation_rejects_shadow_state_length_mismatch(monkeypatch):
    class _BadShadowState:
        def __init__(self, *_args, **_kwargs):
            self.state = np.array([1.0, 0.0, 0.0], dtype=np.complex128)

        def get_num_qubits(self):
            return 1

    monkeypatch.setattr(_run_mod, "ShadowState", _BadShadowState)
    with pytest.raises(ValueError, match="padded shadow state dimension"):
        run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            _zero(),
            total_time=0.1,
            time_steps=3,
            circuit_backend=_UNUSED_BACKEND,
        )


def test_computational_basis_projectors_rejects_negative():
    with pytest.raises(ValueError, match="num_qubits must be non-negative"):
        computational_basis_projectors(-1)


def test_computational_basis_projectors_zero_qubits():
    ops = computational_basis_projectors(0)
    assert len(ops) == 1
    assert ops.operators[0].name == "P_"
    assert ops.operators[0].matrix.shape == (1, 1)


def test_pad_h_s_rejects_non_square():
    with pytest.raises(ValueError, match="H_S must be a square matrix"):
        pad_h_s(np.zeros((2, 3), dtype=np.complex128))


def test_pad_h_s_pads_non_power_of_two():
    h_s = np.arange(9, dtype=np.complex128).reshape(3, 3)
    padded, nq = pad_h_s(h_s)
    assert padded.shape == (4, 4)
    assert nq == 2
    assert np.allclose(padded[:3, :3], h_s)
    assert np.allclose(padded[3, :], 0.0)
    assert np.allclose(padded[:, 3], 0.0)
