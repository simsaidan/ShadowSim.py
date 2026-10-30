"""Tests for the NumPy statevector program engine."""

import numpy as np
import pytest

from shadowsim.backends.numpy_statevector import expectations, sample_counts, statevector
from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Reset, Unitary

_CX = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ],
    dtype=np.complex128,
)


def _rx(theta: float) -> np.ndarray:
    """Return the matrix of an ``RX(theta)`` gate."""
    cosine = np.cos(theta / 2)
    sine = np.sin(theta / 2)
    return np.array(
        [[cosine, -1j * sine], [-1j * sine, cosine]],
        dtype=np.complex128,
    )


def test_ground_state_is_the_zero_ket():
    state = statevector(Program(2, 0, [Barrier([0, 1])]))

    assert state.shape == (4,)
    np.testing.assert_allclose(state, [1, 0, 0, 0])


def test_hadamard_prepares_equal_superposition():
    program = Program(1, 0, [Hadamard(0)])

    np.testing.assert_allclose(np.abs(statevector(program)) ** 2, [0.5, 0.5])
    assert expectations(program, [0], "Z") == pytest.approx([0.0])
    assert expectations(program, [0], "X") == pytest.approx([1.0])


def test_hadamard_on_the_high_qubit_leaves_qubit_zero_in_z():
    program = Program(2, 0, [Hadamard(1)])

    np.testing.assert_allclose(np.abs(statevector(program)) ** 2, [0.5, 0.0, 0.5, 0.0])
    assert expectations(program, [1, 0], "Z") == pytest.approx([0.0, 1.0])
    assert expectations(program, [1], "X") == pytest.approx([1.0])


def test_rx_on_zero_has_the_closed_form_expectations():
    theta = 0.4
    program = Program(1, 0, [Unitary(_rx(theta), [0])])

    assert expectations(program, [0], "Z") == pytest.approx([np.cos(theta)])
    assert expectations(program, [0], "X") == pytest.approx([0.0])


def test_cnot_prepares_a_bell_pair():
    program = Program(2, 0, [Hadamard(0), Unitary(_CX, [0, 1])])
    probabilities = np.abs(statevector(program)) ** 2

    np.testing.assert_allclose(probabilities, [0.5, 0.0, 0.0, 0.5])
    assert expectations(program, [0, 1], "Z") == pytest.approx([0.0, 0.0])


def test_cnot_with_the_control_on_the_high_qubit_flips_qubit_zero():
    program = Program(2, 0, [Prepare([0.0, 1.0], [1]), Unitary(_CX, [1, 0])])

    np.testing.assert_allclose(statevector(program), [0, 0, 0, 1])


def test_two_hadamards_with_a_barrier_return_to_zero():
    program = Program(1, 0, [Hadamard(0), Barrier([0]), Hadamard(0)])

    np.testing.assert_allclose(statevector(program), [1, 0])


def test_prepare_writes_amplitudes_with_qubit_zero_as_the_low_bit():
    low = Program(2, 0, [Prepare([0.0, 1.0], [0])])
    high = Program(2, 0, [Prepare([0.0, 1.0], [1])])

    np.testing.assert_allclose(statevector(low), [0, 1, 0, 0])
    np.testing.assert_allclose(statevector(high), [0, 0, 1, 0])
    assert sample_counts(low, shots=3, seed=0) == {"01": 3}
    assert sample_counts(high, shots=2, seed=1) == {"10": 2}


def test_prepare_of_a_superposition_uses_every_local_bit():
    amplitude = 1.0 / np.sqrt(2.0)
    program = Program(2, 0, [Prepare([amplitude, 0.0, 0.0, amplitude], [0, 1])])

    np.testing.assert_allclose(np.abs(statevector(program)) ** 2, [0.5, 0.0, 0.0, 0.5])


def test_terminal_measure_and_barrier_leave_the_distribution_unchanged():
    program = Program(1, 1, [Hadamard(0), Measure(0, 0), Barrier([0])])

    assert expectations(program, [0], "X") == pytest.approx([1.0])
    assert sum(sample_counts(program, shots=16, seed=None).values()) == 16


def test_sample_counts_repeat_for_the_same_seed():
    program = Program(1, 1, [Hadamard(0), Measure(0, 0)])

    assert sample_counts(program, shots=20, seed=0) == {"1": 12, "0": 8}
    assert sample_counts(program, shots=20, seed=0) == sample_counts(program, shots=20, seed=0)
    assert sample_counts(program, shots=20, seed=1) != sample_counts(program, shots=20, seed=0)


def test_prepare_after_a_gate_is_rejected():
    program = Program(1, 0, [Hadamard(0), Prepare([1.0, 0.0], [0])])

    with pytest.raises(NotImplementedError, match="left \\|0\\.\\.\\.0>"):
        statevector(program)


def test_reset_is_rejected():
    program = Program(1, 0, [Reset(0)])

    with pytest.raises(NotImplementedError, match="Reset is not supported"):
        statevector(program)


def test_measure_followed_by_a_gate_is_rejected():
    program = Program(1, 1, [Measure(0, 0), Hadamard(0)])

    with pytest.raises(NotImplementedError, match="measurement before the end"):
        statevector(program)


def test_expectations_reject_an_unknown_pauli():
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="pauli must be 'X' or 'Z'"):
        expectations(program, [0], "Y")  # type: ignore[arg-type]


@pytest.mark.parametrize("qubit", [True, 1.5, -1, 1])
def test_expectations_reject_a_bad_qubit_index(qubit):
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="outside a program of 1 qubits"):
        expectations(program, [qubit], "Z")


@pytest.mark.parametrize("shots", [True, 1.5, 0, -3])
def test_sample_counts_rejects_a_bad_shot_count(shots):
    program = Program(1, 0, [])

    with pytest.raises(ValueError, match="shots must be a positive integer"):
        sample_counts(program, shots=shots, seed=0)


@pytest.mark.parametrize("seed", [True, "0"])
def test_sample_counts_rejects_a_bad_seed(seed):
    program = Program(1, 0, [])

    with pytest.raises(TypeError, match="seed must be an int or None"):
        sample_counts(program, shots=1, seed=seed)


def test_sample_counts_rejects_probabilities_that_do_not_sum_to_one():
    program = Program(1, 0, [Unitary([[2.0, 0.0], [0.0, 0.0]], [0])])

    with pytest.raises(ValueError, match="probabilities must sum to 1"):
        sample_counts(program, shots=1, seed=0)
