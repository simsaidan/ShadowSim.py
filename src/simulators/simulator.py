from src.core.hamiltonian import Hamiltonian


class Simulator:
    def __init__(
        self, H: Hamiltonian, num_qubits: int, total_time: float, time_steps: int
    ):
        self.H = H
        self.num_qubits = num_qubits
        self.total_time = total_time
        self.time_steps = time_steps
        self.results = None

    def get_results(self, index: int = None):
        pass

    def plot_results(self, index: int = None):
        pass

    def save_result_plot(self, index: int = None):
        pass
