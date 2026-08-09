import numpy as np
import pytest

from shadowsim.core import Operator
from shadowsim.core import OperatorSet
from shadowsim.core import State
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


def test_shadow_state_normalizes_by_a_and_pads_to_next_power_of_two():
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


def test_shadow_state_skips_normalization_when_a_is_zero(monkeypatch):
    """Cover A==0 branch; parent State rejects unnormalized zeros, so stub it."""
    from shadowsim.shadow import shadow_state as module

    captured = {}

    def fake_init(self, state, num_qubits, local_dim=2):
        captured["state"] = np.asarray(state)
        captured["num_qubits"] = num_qubits
        self.state = captured["state"]
        self._num_qubits = num_qubits
        self._local_dim = local_dim

    monkeypatch.setattr(module.State, "__init__", fake_init)
    shadow = ShadowState(_zero(), OperatorSet([Operator(X)]))
    assert shadow.A == 0
    assert np.allclose(captured["state"], np.array([0.0 + 0.0j]))
