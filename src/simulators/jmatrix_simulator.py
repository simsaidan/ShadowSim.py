from src.simulators.simulator import Simulator
from src.core.hamiltonian import Hamiltonian


class JMatrixSimulator(Simulator):
    def __init__(
        self, H: Hamiltonian, num_qubits: int, total_time: float, time_steps: int
    ):
        super().__init__(H, num_qubits, total_time, time_steps)

    def simulate(self):
        pass
