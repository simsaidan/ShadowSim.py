"""Common two-qubit computational-basis states and the 2×2 identity."""

import numpy as np

zero_state_two_qubits = np.array([1, 0, 0, 0])
one_state_two_qubits = np.array([0, 1, 0, 0])
two_state_two_qubits = np.array([0, 0, 1, 0])
three_state_two_qubits = np.array([0, 0, 0, 1])

I = np.eye(2)  # noqa: E741
