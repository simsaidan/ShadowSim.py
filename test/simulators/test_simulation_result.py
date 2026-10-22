"""Tests for SimulationResult and simulator integration."""

import pickle
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, OperatorSet, State
from shadowsim.simulators import SimulationResult
from shadowsim.simulators import result as result_module
from shadowsim.simulators.result import package_version
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
    assert (out / "observables.npz").is_file()
    assert (out / "meta.json").is_file()
    assert not (out / "states.npz").is_file()
    assert not (out / "observables.npy").is_file()
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
    out = result.save(tmp_path / "empty")
    with np.load(out / "observables.npz", allow_pickle=False) as archive:
        assert archive.files == []
    loaded = SimulationResult.load(out)
    assert loaded.observables == []


def test_load_legacy_numeric_observables_npy(tmp_path: Path):
    observables = [np.array([0.0, 1.0]), np.array([1.0, 0.0])]
    result = SimulationResult(
        times=np.array([0.0, 1.0]),
        observables=observables,
        algorithm="legacy",
    )
    out = result.save(tmp_path / "legacy")
    (out / "observables.npz").unlink()
    np.save(out / "observables.npy", np.stack(observables))
    loaded = SimulationResult.load(out)
    assert np.allclose(loaded.observables[0], observables[0])
    assert np.allclose(loaded.observables[1], observables[1])


def test_load_legacy_scalar_and_1d_observables_npy(tmp_path: Path):
    scalar = _load_legacy_observables(tmp_path / "scalar", np.array(3.5))
    assert len(scalar.observables) == 1
    assert np.allclose(scalar.observables[0], [3.5])

    one_d = _load_legacy_observables(tmp_path / "one-d", np.array([1.0, 2.0, 3.0]))
    assert len(one_d.observables) == 1
    assert np.allclose(one_d.observables[0], [1.0, 2.0, 3.0])


def _load_legacy_observables(path: Path, observables: np.ndarray) -> SimulationResult:
    result = SimulationResult(
        times=np.array([0.0]),
        observables=[np.array([1.0])],
        algorithm="legacy",
    )
    out = result.save(path)
    (out / "observables.npz").unlink()
    np.save(out / "observables.npy", observables)
    return SimulationResult.load(out)


_pickle_status = {"executed": False}


def _mark_pickle_executed() -> int:
    _pickle_status["executed"] = True
    return 0


class _ExecutablePickle:
    """Pickle payload that records execution when it is unpickled."""

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (_mark_pickle_executed, ())


def _object_payload() -> np.ndarray:
    payload = np.empty(1, dtype=object)
    payload[0] = _ExecutablePickle()
    return payload


def _prove_payload_executes(path: Path, *, archive: bool) -> None:
    _pickle_status["executed"] = False
    loaded = np.load(path, allow_pickle=True)
    try:
        if archive:
            loaded["arr0"]
    finally:
        if not isinstance(loaded, np.ndarray):
            loaded.close()
    assert _pickle_status["executed"]


def _write_archive_member(path: Path, name: str, values: np.ndarray) -> None:
    buffer = BytesIO()
    np.save(buffer, values)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, buffer.getvalue())


def _saved(path: Path, *, states: bool = False) -> Path:
    result = SimulationResult(
        times=np.array([0.0, 1.0]),
        observables=[np.array([0.25, 0.5])],
        states=[np.array([1.0, 0.0], dtype=np.complex128)] if states else None,
        algorithm="crafted",
    )
    return result.save(path)


def test_load_does_not_unpickle_observables_npz(tmp_path: Path):
    out = _saved(tmp_path / "run")
    path = out / "observables.npz"
    path.unlink()
    np.savez(path, arr0=_object_payload())
    _prove_payload_executes(path, archive=True)
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        SimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_does_not_unpickle_states_npz(tmp_path: Path):
    out = _saved(tmp_path / "run", states=True)
    path = out / "states.npz"
    path.unlink()
    np.savez(path, arr0=_object_payload())
    _prove_payload_executes(path, archive=True)
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        SimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_does_not_unpickle_times_npy(tmp_path: Path):
    out = _saved(tmp_path / "run")
    path = out / "times.npy"
    np.save(path, _object_payload(), allow_pickle=True)
    _prove_payload_executes(path, archive=False)
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        SimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_does_not_unpickle_legacy_observables_npy(tmp_path: Path):
    out = _saved(tmp_path / "run")
    (out / "observables.npz").unlink()
    path = out / "observables.npy"
    np.save(path, _object_payload(), allow_pickle=True)
    _prove_payload_executes(path, archive=False)
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        SimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_does_not_unpickle_raw_pickle_file(tmp_path: Path):
    out = _saved(tmp_path / "run")
    path = out / "times.npy"
    with path.open("wb") as handle:
        pickle.dump(_ExecutablePickle(), handle)
    _pickle_status["executed"] = False
    pickle.loads(path.read_bytes())
    assert _pickle_status["executed"]
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        SimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_rejects_legacy_states_npy_without_reading(tmp_path: Path):
    out = _saved(tmp_path / "run", states=True)
    (out / "states.npz").unlink()
    path = out / "states.npy"
    np.save(path, _object_payload(), allow_pickle=True)
    path.chmod(0)
    _pickle_status["executed"] = False
    try:
        with pytest.raises(ValueError, match="states.npz"):
            SimulationResult.load(out)
    finally:
        path.chmod(0o644)
    assert not _pickle_status["executed"]


def test_save_load_jagged_states(tmp_path: Path):
    states = [
        np.array([1.0, 0.0], dtype=np.complex128),
        np.eye(2, dtype=np.float32),
    ]
    result = SimulationResult(
        times=np.array([0.0, 1.0]),
        observables=[np.array([0.5, 0.5])],
        states=states,
        algorithm="jagged-states",
    )
    loaded = SimulationResult.load(result.save(tmp_path / "jagged-states"))
    assert loaded.states is not None
    assert loaded.states[0].dtype == np.complex128
    assert loaded.states[1].dtype == np.float32
    assert loaded.states[1].shape == (2, 2)
    assert np.allclose(loaded.states[0], states[0])
    assert np.allclose(loaded.states[1], states[1])


def test_save_load_preserves_archive_order(tmp_path: Path):
    observables = [np.array([float(index)]) for index in range(11)]
    loaded = SimulationResult.load(
        SimulationResult(times=np.array([0.0]), observables=observables, algorithm="order").save(tmp_path / "order")
    )
    for index, trace in enumerate(observables):
        assert np.allclose(loaded.observables[index], trace)


def test_empty_states_roundtrip(tmp_path: Path):
    loaded = SimulationResult.load(
        SimulationResult(
            times=np.array([0.0]),
            observables=[np.array([1.0])],
            states=[],
            algorithm="empty-states",
        ).save(tmp_path / "empty-states")
    )
    assert loaded.states == []


def test_save_rejects_non_numeric_state(tmp_path: Path):
    result = SimulationResult(
        times=np.array([0.0]),
        observables=[np.array([1.0])],
        states=[np.array(["q"])],
        algorithm="text",
    )
    with pytest.raises(ValueError, match="numeric"):
        result.save(tmp_path / "text")


def test_load_rejects_non_numeric_state(tmp_path: Path):
    out = _saved(tmp_path / "run", states=True)
    np.savez(out / "states.npz", allow_pickle=False, arr0=np.array(["nope"]))
    with pytest.raises(ValueError, match="numeric"):
        SimulationResult.load(out)


def test_save_replaces_legacy_npy_files(tmp_path: Path):
    out = tmp_path / "run"
    out.mkdir()
    np.save(out / "observables.npy", np.array([1.0]))
    np.save(out / "states.npy", np.array([1.0]))
    SimulationResult(times=np.array([0.0]), observables=[np.array([1.0])], algorithm="new").save(out)
    assert (out / "observables.npz").is_file()
    assert not (out / "observables.npy").exists()
    assert not (out / "states.npy").exists()
    assert not (out / "states.npz").exists()


def test_save_drops_states_archive_when_states_absent(tmp_path: Path):
    out = tmp_path / "run"
    SimulationResult(
        times=np.array([0.0]),
        observables=[np.array([1.0])],
        states=[np.array([1.0, 0.0])],
        algorithm="with",
    ).save(out)
    assert (out / "states.npz").is_file()
    loaded = SimulationResult.load(
        SimulationResult(times=np.array([0.0]), observables=[np.array([1.0])], algorithm="without").save(out)
    )
    assert not (out / "states.npz").exists()
    assert loaded.states is None


def test_load_missing_observables(tmp_path: Path):
    out = _saved(tmp_path / "run")
    (out / "observables.npz").unlink()
    with pytest.raises(FileNotFoundError, match="observables.npz"):
        SimulationResult.load(out)


@pytest.mark.parametrize("name", ["trace", "arrX", "arr\u00b2"])
def test_load_rejects_unexpected_archive_name(tmp_path: Path, name: str):
    out = _saved(tmp_path / "run")
    _write_archive_member(out / "observables.npz", f"{name}.npy", np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="unexpected array"):
        SimulationResult.load(out)


def test_load_reports_a_truncated_archive_member(tmp_path: Path):
    out = _saved(tmp_path / "run")
    buffer = BytesIO()
    np.save(buffer, np.array([1.0, 2.0]))
    with zipfile.ZipFile(out / "observables.npz", "w") as archive:
        archive.writestr("arr0.npy", buffer.getvalue()[:20])
    with pytest.raises(ValueError, match="header"):
        SimulationResult.load(out)


def test_load_rejects_archive_with_a_gap(tmp_path: Path):
    out = _saved(tmp_path / "run")
    np.savez(
        out / "observables.npz",
        allow_pickle=False,
        arr0=np.array([1.0]),
        arr2=np.array([2.0, 3.0]),
    )
    with pytest.raises(ValueError, match="missing an array"):
        SimulationResult.load(out)


def test_load_rejects_npy_bytes_named_as_npz(tmp_path: Path):
    out = _saved(tmp_path / "run")
    array_path = tmp_path / "array.npy"
    np.save(array_path, np.array([[1.0, 2.0]]))
    (out / "observables.npz").write_bytes(array_path.read_bytes())
    with pytest.raises(ValueError, match="array archive"):
        SimulationResult.load(out)


def test_load_rejects_archive_bytes_named_as_times_npy(tmp_path: Path):
    out = _saved(tmp_path / "run")
    archive_path = tmp_path / "times.npz"
    np.savez(archive_path, allow_pickle=False, arr0=np.array([0.0, 1.0]))
    (out / "times.npy").write_bytes(archive_path.read_bytes())
    with pytest.raises(ValueError, match="expected an array"):
        SimulationResult.load(out)


def test_load_reports_a_truncated_times_file(tmp_path: Path):
    out = _saved(tmp_path / "run")
    (out / "times.npy").write_bytes(b"\x93NUMPY")
    with pytest.raises(ValueError) as caught:
        SimulationResult.load(out)
    assert "pickle payload" not in str(caught.value)


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
        num_qubits=1,
        total_time=1.0,
        time_steps=3,
        id="tiny",
    )
    result = sim.simulate()
    assert sim.results == [[0.0, 0.5, 1.0]]
    assert sim.get_results(0) == [0.0, 0.5, 1.0]
    assert result.seed == 3
    assert result.metadata["custom"] == "x"
    assert result.metadata["simulator_id"] == "tiny"
