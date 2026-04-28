from typing import Any, cast

import numpy as np
from qutip import Qobj, mesolve

from src.core.hamiltonian import Hamiltonian, combined_hamiltonian_matrix
from src.core.operator_set import Operator, OperatorSet
from src.core.state import State
from src.simulators.simulator import Simulator


class QutipSimulator(Simulator):
    def __init__(
        self,
        hamiltonians: list[Hamiltonian],
        lindblads: list[Operator],
        initial_state: State,
        observables: OperatorSet | list[Operator],
        num_qubits: int,
        total_time: float,
        time_steps: int,
    ):
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits,
            total_time,
            time_steps,
            "qutip_simulator",
        )
        self.observables = observables

    def simulate(self):
        tlist = self.tlist
        H_q = Qobj(combined_hamiltonian_matrix(self.hamiltonians, self.num_qubits))
        psi0 = Qobj(self.initial_state.state)
        e_ops = [Qobj(op.matrix) for op in self.observables]
        c_ops = [Qobj(op.matrix) for op in self.lindblads]
        # Large energy scales can require more internal integration steps.
        # QuTiP stubs may type ``mesolve`` as ``NoReturn``; avoid marking callers unreachable.
        result = cast(
            Any,
            mesolve(
                H_q,
                psi0,
                tlist,
                c_ops=c_ops,
                e_ops=e_ops,
                options={"nsteps": 100000},
            ),
        )
        self.results = list(result.expect)
        return result

    def __str__(self):
        return (
            "QutipSimulator("
            f"num_qubits={self.num_qubits}, "
            f"observable_count={len(self.observables)}, "
            f"time_steps={self.time_steps}"
            ")"
        )

    def __repr__(self):
        return (
            "QutipSimulator("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"observables={self.observables!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}"
            ")"
        )
