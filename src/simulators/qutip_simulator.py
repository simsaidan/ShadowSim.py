from qutip import mesolve, destroy, basis, tensor, qeye
import numpy as np
import matplotlib.pyplot as plt
from src.simulators.simulator import Simulator
from src.core.hamiltonian import Hamiltonian


class QutipSimulator(Simulator):
    def __init__(
        self, H: Hamiltonian, num_qubits: int, total_time: float, time_steps: int
    ):
        super().__init__(H, num_qubits, total_time, time_steps)
        self.lindblads = []

    def simulate(self):
        tlist = np.linspace(0, self.total_time, self.time_steps)  # simulation times
        initial_state = tensor(basis(N_photons, 1), basis(2, 0))

        # start off with 1 photon in the cavity, atom in ground state
        e_ops = [
            a.dag() * a,
            sm.dag() * sm,
        ]  # operators to evaluate at each time in the simulation

        result = mesolve(
            self.H, initial_state, tlist, self.lindblads, e_ops
        )  # integrate the Lindbladian

        plt.plot(tlist, result.expect[0], label="cavity population")
        plt.plot(tlist, result.expect[1], label="atom population")
        plt.legend()

        plt.xlabel("Time (ns)")
        plt.ylabel("Population")
        plt.title("1 atom resonant Jaynes-Cummings model with loss")
