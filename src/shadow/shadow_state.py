import numpy as np
from src.core.operator_set import OperatorSet
from src.core.state import State


def _ceil_power_of_two(n: int) -> int:
    if n <= 0:
        return 1
    m = 1
    while m < n:
        m <<= 1
    return m


class ShadowState(State):
    def __init__(self, state: State, operator_set: OperatorSet):
        self.A = 0
        exp_vals: list[complex] = []

        for op in operator_set.operators:
            exp_Om = np.trace(op.matrix @ state.get_state())
            self.A += np.abs(exp_Om) ** 2
            exp_vals.append(exp_Om)

        shadow_state = np.asarray(exp_vals, dtype=np.complex128)
        if self.A != 0:
            shadow_state = shadow_state / self.A

        n = int(shadow_state.shape[0])
        padded_len = _ceil_power_of_two(n)
        num_qubits = padded_len.bit_length() - 1
        if n < padded_len:
            out = np.zeros(padded_len, dtype=np.complex128)
            out[:n] = shadow_state
            shadow_state = out

        super().__init__(shadow_state, num_qubits, 2)
