"""QuTiP-backed quantum simulators."""

from typing import Any, cast

from qutip import Qobj, mesolve

from shadowsim.core.combined_hamiltonian_matrix import combined_hamiltonian_matrix
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.operator import Operator
from shadowsim.core.operator_set import OperatorSet
from shadowsim.core.state import State
from shadowsim.simulators.simulator import Simulator


class QutipSimulator(Simulator):
    """Simulate open or closed quantum dynamics with QuTiP."""

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
        """Initialize a QuTiP simulator for the given model."""
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
        """Evolve the system with QuTiP and store expectation traces."""
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
        """Return a string representation of the QutipSimulator."""
        return (
            "QutipSimulator("
            f"num_qubits={self.num_qubits}, "
            f"observable_count={len(self.observables)}, "
            f"time_steps={self.time_steps}"
            ")"
        )

    def __repr__(self):
        """Return a string representation of the QutipSimulator."""
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
