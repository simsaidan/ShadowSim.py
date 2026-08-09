import numpy as np
import pytest

import shadowsim.simulators.splitjmatrix_simulator as splitjmatrix_module
from shadowsim.core import LocalHamiltonian
from shadowsim.core import State
from shadowsim.simulators import SplitJMatrixSimulator


Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def _simulator(*, verbose=False, shots=10000):
    return SplitJMatrixSimulator(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        total_time=1.0,
        time_steps=2,
        num_steps=1,
        verbose=verbose,
        shots=shots,
    )


def test_splitjmatrix_simulator_is_quiet_by_default(monkeypatch, capsys):
    verbose_values = []

    def fake_split_jmatrix(*args, **kwargs):
        verbose_values.append(kwargs["verbose"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator().simulate()

    assert capsys.readouterr().out == ""
    assert verbose_values == [False, False]


def test_splitjmatrix_simulator_reports_progress_when_verbose(monkeypatch, capsys):
    verbose_values = []

    def fake_split_jmatrix(*args, **kwargs):
        verbose_values.append(kwargs["verbose"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(verbose=True).simulate()

    output = capsys.readouterr().out
    assert "Working on time step 0.0" in output
    assert "Working on time step 1.0" in output
    assert verbose_values == [True, True]


def test_splitjmatrix_simulator_forwards_shots(monkeypatch):
    seen_shots = []

    def fake_split_jmatrix(*args, **kwargs):
        seen_shots.append(kwargs["shots"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(shots=1234).simulate()

    assert seen_shots == [1234, 1234]


def test_splitjmatrix_simulator_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _simulator(shots=0)
