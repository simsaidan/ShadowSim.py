"""Tests for SimulationResult and simulator integration."""

from pathlib import Path

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, OperatorSet, State
from shadowsim.simulators import SimulationResult
from shadowsim.simulators import result as result_module
from shadowsim.simulators.result import (
    _observables_from_npy,
    _observables_to_npy,
    _states_from_npy,
    package_version,
)
from shadowsim.simulators.simulator import Simulator

Z = np.diag([1.0, -1.0]).astype(np.complex128)


def _qutip_tiny(**kwargs):
    pytest.importorskip("qutip")
    from shadowsim.simulators import QutipSimulator

    defaults = {
        "hamiltonians": [Hamiltonian(Z)],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "observables": OperatorSet([Operator(Z, name="Z")]),
        "num_qubits": 1,
        "total_time": 0.1,
        "time_steps": 5,
    }
    defaults.update(kwargs)
    return QutipSimulator(**defaults)


def test_simulation_result_save_load_roundtrip(tmp_path: Path):
    times = np.linspace(0.0, 1.0, 4)
    observables = [np.array([0.0, 0.1, 0.2, 0.3]), np.array([1.0, 0.9, 0.8, 0.7])]
    result = SimulationResult(
        times=times,
        observables=observables,
        states=None,
        seed=7,
        algorithm="demo",
        runtime=0.0123,
        metadata={"software_version": "0.1.0", "num_qubits": 1},
    )
    out = result.save(tmp_path / "run")
    assert (out / "times.npy").is_file()
    assert (out / "observables.npy").is_file()
    assert (out / "meta.json").is_file()
    assert not (out / "states.npy").is_file()

    loaded = SimulationResult.load(out)
    assert np.allclose(loaded.times, times)
    assert len(loaded.observables) == 2
    assert np.allclose(loaded.observables[0], observables[0])
    assert np.allclose(loaded.observables[1], observables[1])
    assert loaded.states is None
    assert loaded.seed == 7
    assert loaded.algorithm == "demo"
    assert loaded.runtime == pytest.approx(0.0123)
    assert loaded.metadata["num_qubits"] == 1


def test_simulation_result_save_load_with_states(tmp_path: Path):
    times = np.array([0.0, 1.0])
    observables = [np.array([0.5, 0.5])]
    states = [
        np.array([1.0, 0.0], dtype=np.complex128),
        np.array([0.0, 1.0], dtype=np.complex128),
    ]
    result = SimulationResult(
        times=times,
        observables=observables,
        states=states,
        algorithm="with_states",
        metadata={},
    )
    loaded = SimulationResult.load(result.save(tmp_path / "with_states"))
    assert loaded.states is not None
    assert len(loaded.states) == 2
    assert np.allclose(loaded.states[0], states[0])
    assert np.allclose(loaded.states[1], states[1])


def test_simulation_result_save_load_jagged_observables(tmp_path: Path):
    result = SimulationResult(
        times=np.array([0.0, 1.0, 2.0]),
        observables=[np.array([1.0, 2.0]), np.array([3.0, 4.0, 5.0])],
        algorithm="jagged",
    )
    loaded = SimulationResult.load(result.save(tmp_path / "jagged"))
    assert np.allclose(loaded.observables[0], [1.0, 2.0])
    assert np.allclose(loaded.observables[1], [3.0, 4.0, 5.0])


def test_simulation_result_load_missing_dir(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="directory not found"):
        SimulationResult.load(tmp_path / "missing")


def test_simulation_result_load_missing_meta_json(tmp_path: Path):
    out = tmp_path / "no_meta"
    out.mkdir()
    np.save(out / "times.npy", np.array([0.0, 1.0]))
    np.save(out / "observables.npy", np.array([[0.0, 1.0]]))
    with pytest.raises(FileNotFoundError, match="missing meta.json"):
        SimulationResult.load(out)


def test_simulation_result_load_missing_states_file(tmp_path: Path):
    out = tmp_path / "claimed_states"
    result = SimulationResult(
        times=np.array([0.0, 1.0]),
        observables=[np.array([0.5, 0.5])],
        algorithm="claim",
    )
    result.save(out)
    meta_path = out / "meta.json"
    meta = meta_path.read_text(encoding="utf-8").replace('"has_states": false', '"has_states": true')
    meta_path.write_text(meta, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="claims states"):
        SimulationResult.load(out)


def test_simulation_result_empty_observables_roundtrip(tmp_path: Path):
    result = SimulationResult(
        times=np.array([0.0, 1.0]),
        observables=[],
        algorithm="empty",
    )
    packed = _observables_to_npy([])
    assert packed.shape == (0, 0)
    loaded = SimulationResult.load(result.save(tmp_path / "empty"))
    assert loaded.observables == []


def test_observables_from_npy_scalar_and_1d():
    assert len(_observables_from_npy(np.array(3.5))) == 1
    assert np.allclose(_observables_from_npy(np.array(3.5))[0], [3.5])
    one_d = _observables_from_npy(np.array([1.0, 2.0, 3.0]))
    assert len(one_d) == 1
    assert np.allclose(one_d[0], [1.0, 2.0, 3.0])


def test_states_from_npy_non_object_array():
    raw = np.array([1.0, 0.0], dtype=np.complex128)
    loaded = _states_from_npy(raw)
    assert len(loaded) == 1
    assert np.allclose(loaded[0], raw)


def test_package_version_unknown_when_missing(monkeypatch):
    def _raise(_name: str):
        raise result_module.PackageNotFoundError("shadowsim")

    monkeypatch.setattr(result_module, "version", _raise)
    assert package_version() == "unknown"


@pytest.mark.qutip
def test_qutip_simulate_returns_simulation_result():
    sim = _qutip_tiny()
    result = sim.simulate()
    assert isinstance(result, SimulationResult)
    assert sim.last_result is result
    assert result.algorithm == "qutip_simulator"
    assert result.seed is None
    assert result.runtime is not None and result.runtime >= 0.0
    assert result.states is None
    assert np.allclose(result.times, sim.tlist)
    assert len(result.observables) == 1
    assert result.observables[0].shape == (5,)
    assert sim.results is not None
    assert len(sim.results) == 1
    assert result.metadata["software_version"] == package_version()
    assert result.metadata["num_qubits"] == 1
    assert result.metadata["time_steps"] == 5
    assert result.metadata["simulator_id"] == "qutip_simulator"
    assert result.metadata["observable_count"] == 1


def test_make_result_stores_last_result_and_keeps_traces():
    class Tiny(Simulator):
        def simulate(self):
            traces = [[0.0, 0.5, 1.0]]
            self.results = traces
            return self._make_result(traces, runtime=0.1, seed=3, custom="x")

    sim = Tiny(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        1.0,
        3,
        "tiny",
    )
    result = sim.simulate()
    assert sim.results == [[0.0, 0.5, 1.0]]
    assert sim.get_results(0) == [0.0, 0.5, 1.0]
    assert result.seed == 3
    assert result.metadata["custom"] == "x"
    assert result.metadata["simulator_id"] == "tiny"
