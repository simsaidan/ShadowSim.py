"""Encoded states are valid simulator initial states."""

import numpy as np
import numpy.typing as npt
import pytest

from shadowsim.core import Hamiltonian, State
from shadowsim.encoding import AmplitudeEncoding, AngleEncoding, ComputationalBasisEncoding
from shadowsim.encoding.state_encoder import StateEncoder
from shadowsim.simulators.simulator import Simulator

_Z = np.diag([1.0, -1.0]).astype(np.complex128)


def test_state_encoder_encode_is_not_implemented():
    class _Passthrough(StateEncoder):
        def encode(self, data: npt.ArrayLike) -> State:
            return super().encode(data)

    with pytest.raises(NotImplementedError):
        _Passthrough().encode([1.0])


@pytest.mark.parametrize(
    "state",
    [
        ComputationalBasisEncoding(1).encode(1),
        AngleEncoding().encode([0.4]),
        AmplitudeEncoding().encode([0.3, 0.4]),
    ],
    ids=["basis", "angle", "amplitude"],
)
def test_encoded_state_is_simulator_initial_state(state):
    sim = Simulator(
        [Hamiltonian(_Z)],
        [],
        state,
        num_qubits=state.get_num_qubits(),
        total_time=1.0,
        time_steps=2,
        id="encoding",
    )
    assert sim.initial_state is state
    assert sim.num_qubits == state.get_num_qubits()
    assert np.isclose(np.linalg.norm(state.to_numpy()), 1.0)
