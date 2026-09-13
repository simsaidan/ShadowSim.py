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


def _zero() -> State:
    return State(np.array([1.0, 0.0], dtype=np.complex128), 1)


def test_run_shadow_simulation_one_qubit_known_h_s():
    result = run_shadow_simulation(
        Hamiltonian(X),
        OperatorSet([Operator(Z)]),
        _zero(),
        total_time=1.0,
        time_steps=11,
    )

    assert isinstance(result, ShadowSimulationResult)
    assert result.shadow_hamiltonian.basis == ["Y", "Z"]
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)
    assert np.allclose(result.H_S_padded, EXPECTED_H_S)
    assert result.shadow_num_qubits == 1
    assert result.times.shape == (11,)
    assert len(result.expectations) == 2
    assert result.labels == ["P_0", "P_1"]
    for trace in result.expectations:
        assert trace.shape == (11,)


def test_run_shadow_simulation_sparse_labels_path():
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=0.5,
        time_steps=5,
    )
    assert result.shadow_hamiltonian.used_sparse_pauli_path is True
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)
    assert result.shadow_num_qubits == 1


def test_run_shadow_simulation_accepts_observable_sequence():
    """Sequence observables coerce via `_as_operator_set` (not only OperatorSet)."""
    result = run_shadow_simulation(
        Hamiltonian("X"),
        ["Z"],
        _zero(),
        total_time=0.5,
        time_steps=5,
    )
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)


def test_run_shadow_simulation_local_hamiltonian_skips_dim_check():
    """LocalHamiltonian terms are skipped in physical-dimension validation."""
    result = run_shadow_simulation(
        [LocalHamiltonian(X, [0])],
        OperatorSet([Operator(Z)]),
        _zero(),
        total_time=0.5,
        time_steps=5,
        num_qubits=1,
    )
    assert result.shadow_hamiltonian.used_sparse_pauli_path is False
    assert np.allclose(result.shadow_hamiltonian.H_S, EXPECTED_H_S)


def test_run_shadow_simulation_custom_shadow_observables():
    projectors = computational_basis_projectors(1)
    result = run_shadow_simulation(
        Hamiltonian("X"),
        OperatorSet(["Z"]),
        _zero(),
        total_time=0.5,
        time_steps=5,
        shadow_observables=projectors,
    )
    assert result.labels == ["P_0", "P_1"]
    assert len(result.expectations) == 2


def test_run_shadow_simulation_rejects_empty_hamiltonians():
    with pytest.raises(ValueError, match="shadow simulation: hamiltonians"):
        run_shadow_simulation(
            [],
            OperatorSet([Operator(Z)]),
            _zero(),
            total_time=0.1,
            time_steps=3,
        )


def test_run_shadow_simulation_rejects_empty_observables():
    with pytest.raises(ValueError, match="shadow simulation: observables"):
        run_shadow_simulation(
            Hamiltonian(X),
            OperatorSet([]),
            _zero(),
            total_time=0.1,
            time_steps=3,
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
