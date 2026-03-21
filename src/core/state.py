import numpy as np


class State:
    def __init__(self, state: np.ndarray):
        self.state = state

    def get_state(self):
        return self.state

    def set_state(self, state: np.ndarray):
        self.state = state

    def get_num_qubits(self):
        pass
