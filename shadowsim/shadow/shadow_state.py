"""Shadow states from operator expectation values."""

import numpy as np

from shadowsim.core.operator_set import OperatorSet
from shadowsim.core.state import State
from shadowsim.utils.next_power_of_two import next_power_of_two


class ShadowState(State):
    """Represent a shadow state built from operator expectation values."""

    def __init__(
        self,
        state: State,
        operator_set: OperatorSet,
        *,
        num_qubits: int | None = None,
    ):
        """Initialize a ShadowState from a state and operator set."""
        self.A = 0
        exp_vals: list[complex] = []

        psi = state.get_state()
        for op in operator_set.operators:
            exp_Om = np.vdot(psi, op.matrix @ psi)
            self.A += np.abs(exp_Om) ** 2
            exp_vals.append(exp_Om)

        shadow_state = np.asarray(exp_vals, dtype=np.complex128)
        if self.A != 0:
            shadow_state = shadow_state / self.A

        n = int(shadow_state.shape[0])
        if num_qubits is not None:
            nq = int(num_qubits)
            if nq < 0:
                raise ValueError("num_qubits must be non-negative")
            need = 2**nq
            if n > need:
                raise ValueError(f"not enough room in 2**num_qubits={need} for {n} shadow components")
            padded_len = need
        else:
            padded_len = next_power_of_two(n)
        num_qubits_out = padded_len.bit_length() - 1
        if int(shadow_state.shape[0]) < padded_len:
            out = np.zeros(padded_len, dtype=np.complex128)
            out[:n] = shadow_state
            shadow_state = out

        super().__init__(shadow_state, num_qubits_out, 2)

    def __str__(self):
        """Return a string representation of the ShadowState."""
        return f"ShadowState(num_qubits={self.get_num_qubits()}, A={self.A}, shape={self.state.shape})"

    def __repr__(self):
        """Return a string representation of the ShadowState."""
        return f"ShadowState(state={self.state!r}, A={self.A!r}, num_qubits={self.get_num_qubits()})"
