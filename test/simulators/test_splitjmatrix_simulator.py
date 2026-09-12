import numpy as np
import pytest

import shadowsim.simulators.splitjmatrix_simulator as splitjmatrix_module
from shadowsim.core import LocalHamiltonian, Operator, State
from shadowsim.simulators import SplitJMatrixSimulator
from shadowsim.simulators.splitjmatrix_simulator import (
    _split_jmatrix,
    _trace_qubits,
    cavity_population,
    population_one,
)

Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def _simulator(*, verbose=False, shots=10000, **kwargs):
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
        **kwargs,
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


def test_splitjmatrix_simulator_forwards_seed(monkeypatch):
    seen_seeds = []

    def fake_split_jmatrix(*args, **kwargs):
        seen_seeds.append(kwargs["seed"])
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(seed=7).simulate()

    assert seen_seeds == [7, 7]


def test_splitjmatrix_simulator_progress_callback(monkeypatch):
    seen = []

    def fake_split_jmatrix(*args, **kwargs):
        return {"0": 10}

    monkeypatch.setattr(splitjmatrix_module, "_split_jmatrix", fake_split_jmatrix)

    _simulator(progress=lambda step, total: seen.append((step, total))).simulate()

    assert seen == [(0, 2), (1, 2)]


def test_splitjmatrix_simulator_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _simulator(shots=0)


def test_splitjmatrix_simulator_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _simulator(seed=1.5)  # type: ignore[arg-type]


def test_trace_qubits_accepts_single_int_index():
    assert _trace_qubits({"01": 3, "11": 2}, 1) == {"1": 5}


def test_population_one_and_cavity_population_empty_counts():
    assert population_one({}) == 0.0
    assert cavity_population({}) == 0.0


def test_split_jmatrix_rejects_nonpositive_shots():
    with pytest.raises(ValueError, match="shots must be a positive integer"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=0,
        )


def test_split_jmatrix_rejects_non_int_seed():
    with pytest.raises(TypeError, match="seed must be an int or None"):
        _split_jmatrix(
            [LocalHamiltonian(Z, [0])],
            [],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            t=0.0,
            num_steps=1,
            shots=1,
            seed=1.5,  # type: ignore[arg-type]
        )


def _fake_aer_backend(monkeypatch, ctor_kwargs_log=None):
    class FakeResult:
        def get_counts(self):
            return {"0": 1}

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeBackend:
        def __init__(self, **kwargs):
            if ctor_kwargs_log is not None:
                ctor_kwargs_log.append(kwargs)

        def run(self, compiled, shots):
            return FakeJob()

    monkeypatch.setattr(splitjmatrix_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(splitjmatrix_module, "transpile", lambda circ, backend: circ)


def test_split_jmatrix_verbose_prints_iterations(monkeypatch, capsys):
    _fake_aer_backend(monkeypatch)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        verbose=True,
        shots=1,
    )

    assert "Working on iteration 0 out of 1" in capsys.readouterr().out


def test_split_jmatrix_passes_seed_simulator(monkeypatch):
    ctor_kwargs = []
    _fake_aer_backend(monkeypatch, ctor_kwargs_log=ctor_kwargs)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=7,
    )

    assert ctor_kwargs == [{"seed_simulator": 7}]


def test_split_jmatrix_omits_seed_when_none(monkeypatch):
    ctor_kwargs = []
    _fake_aer_backend(monkeypatch, ctor_kwargs_log=ctor_kwargs)

    _split_jmatrix(
        [LocalHamiltonian(Z, [0])],
        [],
        State(np.array([1.0, 0.0]), 1),
        num_qubits=1,
        t=0.0,
        num_steps=1,
        shots=1,
        seed=None,
    )

    assert ctor_kwargs == [{}]


def test_splitjmatrix_simulator_rejects_non_local_lindblad():
    with pytest.raises(TypeError, match="must be LocalOperator"):
        SplitJMatrixSimulator(
            [LocalHamiltonian(Z, [0])],
            [Operator(Z)],
            State(np.array([1.0, 0.0]), 1),
            num_qubits=1,
            total_time=1.0,
            time_steps=2,
            num_steps=1,
        )


def test_splitjmatrix_simulator_rejects_mismatched_reducers():
    with pytest.raises(ValueError, match="reducers and measurement_groups must have the same length"):
        _simulator(measurement_groups=[0], reducers=[population_one, population_one])


def test_splitjmatrix_simulator_str_and_repr():
    sim = _simulator(shots=42, seed=7)
    text = str(sim)
    rep = repr(sim)
    assert "SplitJMatrixSimulator(" in text
    assert "shots=42" in text
    assert "seed=7" in text
    assert "SplitJMatrixSimulator(" in rep
    assert "shots=42" in rep
    assert "seed=7" in rep
    assert "progress=" in rep
