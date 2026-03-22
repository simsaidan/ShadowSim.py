import numpy as np
from qutip import Qobj, mesolve

from src.core.hamiltonian import Hamiltonian
from src.core.operator_set import Operator
from src.core.state import State
from src.simulators.simulator import Simulator


class QutipSimulator(Simulator):
    def __init__(
        self,
        H: Hamiltonian,
        initial_state: State,
        observables: list[Operator],
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
            "qutip_simulator",
        )
        self.observables = observables
        self.lindblads = []

    def simulate(self):
        tlist = self.tlist
        H_q = Qobj(self.H.matrix)
        psi0 = Qobj(self.initial_state.state)
        e_ops = [Qobj(op.matrix) for op in self.observables]
        result = mesolve(H_q, psi0, tlist, self.lindblads, e_ops)
        self.results = list(result.expect)
        return result
