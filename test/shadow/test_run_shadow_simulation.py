import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, OperatorSet, State
from shadowsim.shadow import ShadowSimulationResult, run_shadow_simulation

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
