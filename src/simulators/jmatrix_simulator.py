from src.core.hamiltonian import Hamiltonian
from src.core.state import State
from src.simulators.simulator import Simulator


class JMatrixSimulator(Simulator):
    def __init__(
        self,
        H: Hamiltonian,
        initial_state: State,
        num_qubits: int,
        total_time: float,
        time_steps: int,
    ):
        super().__init__(
            H,
            initial_state,
            num_qubits,
            total_time,
            time_steps,
            "jmatrix_simulator",
        )

    def simulate(self):
        pass
