import numpy as np
import pytest

from shadowsim.core import Operator, OperatorSet, State
from shadowsim.shadow import ShadowState

X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def _zero() -> State:
    return State(np.array([1.0, 0.0], dtype=np.complex128), 1)


def _plus() -> State:
    return State(
        np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2),
        1,
    )


def test_shadow_state_single_expectation_is_unit_and_pads_nothing():
    """|0⟩ with {Z}: ⟨Z⟩=1 ⇒ A=1 and shadow = |0⟩ in a 1-dim (0-qubit) space."""
    shadow = ShadowState(_zero(), OperatorSet([Operator(Z)]))

    assert shadow.A == pytest.approx(1.0)
    assert shadow.get_num_qubits() == 0
    assert np.allclose(shadow.to_numpy(), np.array([1.0 + 0.0j]))


def test_shadow_state_unit_weight_pads_to_next_power_of_two():
    """|+⟩ with {X, Y, Z}: only ⟨X⟩≠0, A=1, three components pad to length 4."""
    shadow = ShadowState(
        _plus(),
        OperatorSet([Operator(X), Operator(Y), Operator(Z)]),
    )

    assert shadow.A == pytest.approx(1.0)
    assert shadow.get_num_qubits() == 2
    expected = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    assert np.allclose(shadow.to_numpy(), expected)


def test_shadow_state_explicit_num_qubits_pads_with_zeros():
    shadow = ShadowState(
        _zero(),
        OperatorSet([Operator(Z)]),
        num_qubits=2,
    )

    assert shadow.A == pytest.approx(1.0)
    assert shadow.get_num_qubits() == 2
    expected = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    assert np.allclose(shadow.to_numpy(), expected)


def test_shadow_state_rejects_negative_num_qubits():
    with pytest.raises(ValueError, match="num_qubits must be non-negative"):
        ShadowState(_zero(), OperatorSet([Operator(Z)]), num_qubits=-1)


def test_shadow_state_rejects_num_qubits_too_small_for_components():
    with pytest.raises(ValueError, match="not enough room"):
        ShadowState(
            _plus(),
            OperatorSet([Operator(X), Operator(Y), Operator(Z)]),
            num_qubits=1,
        )


def test_shadow_state_str_and_repr():
    shadow = ShadowState(_zero(), OperatorSet([Operator(Z)]), num_qubits=1)

    text = str(shadow)
    rep = repr(shadow)
    assert "ShadowState(" in text
    assert "num_qubits=1" in text
    assert "A=" in text
    assert "shape=(2,)" in text
    assert "ShadowState(" in rep
    assert "A=" in rep
    assert "num_qubits=1" in rep


def test_shadow_state_normalizes_by_sqrt_a():
    """|0⟩ with {Z, I}: ⟨Z⟩=⟨I⟩=1 so A=2, and [1, 1]/2 is not a unit vector."""
    identity = np.eye(2, dtype=np.complex128)
    shadow = ShadowState(_zero(), OperatorSet([Operator(Z), Operator(identity)]))

    assert shadow.A == pytest.approx(2.0)
    expected = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2.0)
    assert np.allclose(shadow.to_numpy(), expected)


def test_shadow_state_preserves_relative_signs_when_normalizing():
    """|1⟩ with {Z, I}: ⟨Z⟩=-1, ⟨I⟩=1, A=2, shadow = [-1, 1]/√2."""
    identity = np.eye(2, dtype=np.complex128)
    one = State(np.array([0.0, 1.0], dtype=np.complex128), 1)
    shadow = ShadowState(one, OperatorSet([Operator(Z), Operator(identity)]))

    assert shadow.A == pytest.approx(2.0)
    expected = np.array([-1.0, 1.0], dtype=np.complex128) / np.sqrt(2.0)
    assert np.allclose(shadow.to_numpy(), expected)


def test_shadow_state_normalizes_partial_expectation():
    """⟨Y⟩=0 and ⟨Z⟩=1/2 give A=1/4, so the shadow vector is [0, 1]."""
    theta = np.pi / 3
    ket = np.array([np.cos(theta / 2), np.sin(theta / 2)], dtype=np.complex128)
    shadow = ShadowState(State(ket, 1), OperatorSet([Operator(Y), Operator(Z)]))

    assert shadow.A == pytest.approx(0.25)
    expected = np.array([0.0, 1.0], dtype=np.complex128)
    assert np.allclose(shadow.to_numpy(), expected)


def test_shadow_state_rejects_zero_amplitude_weight():
    """|0⟩ with {X}: ⟨X⟩=0 so A=0 and no unit shadow vector exists."""
    with pytest.raises(ValueError, match=r"A = Σ\|⟨O⟩\|² is zero"):
        ShadowState(_zero(), OperatorSet([Operator(X)]))
