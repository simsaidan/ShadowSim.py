"""Save, load, and plot tests for shadow simulation results."""

import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from shadowsim.core import Hamiltonian, OperatorSet, State
from shadowsim.shadow import ShadowSimulationResult, run_shadow_simulation

_run_mod = importlib.import_module("shadowsim.shadow.run_shadow_simulation")

_pickle_status = {"executed": False}


def _mark_pickle_executed() -> int:
    _pickle_status["executed"] = True
    return 0


class _ExecutablePickle:
    """Pickle payload that records execution when it is unpickled."""

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (_mark_pickle_executed, ())


def _result(**overrides: object) -> ShadowSimulationResult:
    values: dict[str, object] = {
        "times": np.array([0.0, 0.5, 1.0]),
        "expectations": [np.array([0.0, 0.2, 0.4]), np.array([1.0, 0.8, 0.6])],
        "labels": ["P_0", "P_1"],
        "basis": ["X", "Y", "Z"],
        "shadow_num_qubits": 2,
        "h_s_dimension": 3,
        "H_S_padded": np.eye(4, dtype=np.complex128),
    }
    values.update(overrides)
    return ShadowSimulationResult(**values)  # type: ignore[arg-type]


def _saved(path: Path, **overrides: object) -> Path:
    return _result(**overrides).save(path)


def _rewrite_meta(path: Path, **updates: object) -> None:
    meta_path = path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(updates)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def test_save_load_roundtrip(tmp_path: Path) -> None:
    source = _result()
    out = source.save(tmp_path / "run")

    assert sorted(path.name for path in out.iterdir()) == ["expectations.npy", "meta.json", "times.npy"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta == {
        "basis": ["X", "Y", "Z"],
        "h_s_dimension": 3,
        "labels": ["P_0", "P_1"],
        "shadow_num_qubits": 2,
    }
    stored = np.load(out / "expectations.npy")
    assert stored.shape == (2, 3)
    assert stored.dtype == np.float64

    loaded = ShadowSimulationResult.load(out)
    assert loaded.shadow_hamiltonian is None
    assert loaded.shadow_state is None
    assert loaded.H_S_padded is None
    assert loaded.labels == source.labels
    assert loaded.basis == source.basis
    assert loaded.shadow_num_qubits == source.shadow_num_qubits
    assert loaded.h_s_dimension == source.h_s_dimension
    assert np.allclose(loaded.times, source.times)
    assert len(loaded.expectations) == len(source.expectations)
    for loaded_curve, source_curve in zip(loaded.expectations, source.expectations, strict=True):
        assert np.allclose(loaded_curve, source_curve)


def test_save_load_empty_curves(tmp_path: Path) -> None:
    loaded = ShadowSimulationResult.load(
        _saved(
            tmp_path / "empty",
            expectations=[],
            labels=[],
            basis=[],
            shadow_num_qubits=0,
            h_s_dimension=0,
            H_S_padded=None,
        )
    )
    assert loaded.expectations == []
    assert loaded.labels == []
    assert loaded.basis == []
    assert loaded.shadow_num_qubits == 0
    assert loaded.h_s_dimension == 0
    assert loaded.times.shape == (3,)


def test_save_rejects_label_count_mismatch(tmp_path: Path) -> None:
    result = _result(labels=["P_0"])
    with pytest.raises(ValueError, match="labels and expectations disagree"):
        result.save(tmp_path / "run")


def test_save_rejects_curve_length_mismatch(tmp_path: Path) -> None:
    result = _result(labels=["P_0"], expectations=[np.array([0.0, 1.0])])
    with pytest.raises(ValueError, match="expectation length disagrees with times"):
        result.save(tmp_path / "run")


def test_save_rejects_a_non_flat_curve(tmp_path: Path) -> None:
    result = _result(labels=["P_0"], expectations=[np.ones((3, 1))])
    with pytest.raises(ValueError, match="expectation length disagrees with times"):
        result.save(tmp_path / "run")


def test_save_rejects_non_flat_times(tmp_path: Path) -> None:
    result = _result(times=np.ones((3, 1)))
    with pytest.raises(ValueError, match="times must be a 1D array"):
        result.save(tmp_path / "run")


def test_save_rejects_a_complex_curve(tmp_path: Path) -> None:
    result = _result(labels=["P_0"], expectations=[np.array([1.0, 2.0, 3.0], dtype=np.complex128)])
    with pytest.raises(ValueError, match="real numeric array"):
        result.save(tmp_path / "run")


def test_save_rejects_an_object_curve(tmp_path: Path) -> None:
    result = _result(labels=["only"], expectations=[np.array([object(), object(), object()], dtype=object)])
    with pytest.raises(ValueError, match="real numeric array"):
        result.save(tmp_path / "run")


def test_load_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="directory not found"):
        ShadowSimulationResult.load(tmp_path / "missing")


def test_load_missing_meta_json(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    (out / "meta.json").unlink()
    with pytest.raises(FileNotFoundError, match="missing meta.json"):
        ShadowSimulationResult.load(out)


@pytest.mark.parametrize("name", ["times.npy", "expectations.npy"])
def test_load_missing_array_file(tmp_path: Path, name: str) -> None:
    out = _saved(tmp_path / "run")
    (out / name).unlink()
    with pytest.raises(FileNotFoundError, match=f"missing {name}"):
        ShadowSimulationResult.load(out)


def test_load_does_not_unpickle_expectations(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    payload = np.empty(1, dtype=object)
    payload[0] = _ExecutablePickle()
    np.save(out / "expectations.npy", payload, allow_pickle=True)
    _pickle_status["executed"] = False
    np.load(out / "expectations.npy", allow_pickle=True)
    assert _pickle_status["executed"]
    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="pickle payload"):
        ShadowSimulationResult.load(out)
    assert not _pickle_status["executed"]


def test_load_reraises_a_non_pickle_array_error(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    (out / "times.npy").write_bytes(b"\x93NUMPY")
    with pytest.raises(ValueError) as caught:
        ShadowSimulationResult.load(out)
    assert "pickle payload" not in str(caught.value)


def test_load_rejects_an_archive_named_as_expectations(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    archive = tmp_path / "expectations.npz"
    np.savez(archive, arr0=np.array([0.0, 1.0, 2.0]))
    (out / "expectations.npy").write_bytes(archive.read_bytes())
    with pytest.raises(ValueError, match="expected an array"):
        ShadowSimulationResult.load(out)


def test_load_rejects_a_non_array_without_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = _saved(tmp_path / "run")
    original = _run_mod.np.load

    def fake_load(path: Path, allow_pickle: bool = False) -> object:
        if Path(path).name == "expectations.npy":
            return object()
        return original(path, allow_pickle=allow_pickle)

    monkeypatch.setattr(_run_mod.np, "load", fake_load)
    with pytest.raises(ValueError, match="expected an array"):
        ShadowSimulationResult.load(out)


def test_load_rejects_a_non_object_meta(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    (out / "meta.json").write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="meta.json must be an object"):
        ShadowSimulationResult.load(out)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("labels", "P_0", "labels must be a list of strings"),
        ("labels", ["P_0", 1], "labels must be a list of strings"),
        ("basis", None, "basis must be a list of strings"),
        ("shadow_num_qubits", True, "shadow_num_qubits must be a non-negative integer"),
        ("shadow_num_qubits", 1.5, "shadow_num_qubits must be a non-negative integer"),
        ("h_s_dimension", -1, "h_s_dimension must be a non-negative integer"),
    ],
)
def test_load_rejects_malformed_meta(tmp_path: Path, field: str, value: object, match: str) -> None:
    out = _saved(tmp_path / "run")
    _rewrite_meta(out, **{field: value})
    with pytest.raises(ValueError, match=match):
        ShadowSimulationResult.load(out)


def test_load_rejects_basis_length_mismatch(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    _rewrite_meta(out, basis=["X"])
    with pytest.raises(ValueError, match="basis length disagrees"):
        ShadowSimulationResult.load(out)


def test_load_rejects_padding_mismatch(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    _rewrite_meta(out, shadow_num_qubits=1)
    with pytest.raises(ValueError, match="shadow padding disagrees"):
        ShadowSimulationResult.load(out)


def test_load_rejects_a_one_dimensional_expectations_file(tmp_path: Path) -> None:
    out = _saved(tmp_path / "run")
    np.save(out / "expectations.npy", np.array([0.0, 0.5, 1.0]))
    with pytest.raises(ValueError, match="must be a 2D array"):
        ShadowSimulationResult.load(out)


@pytest.mark.parametrize("shape", [(1, 3), (2, 2)])
def test_load_rejects_an_expectations_shape_mismatch(tmp_path: Path, shape: tuple[int, int]) -> None:
    out = _saved(tmp_path / "run")
    np.save(out / "expectations.npy", np.ones(shape))
    with pytest.raises(ValueError, match="disagrees with labels and times"):
        ShadowSimulationResult.load(out)


def test_plot_results_requires_the_viz_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(module: str, *, extra: str) -> None:
        raise ImportError(f"{module} requires the {extra} extra. Install it with: pip install 'shadowsim[{extra}]'")

    monkeypatch.setattr(_run_mod, "import_optional", missing)
    with pytest.raises(ImportError, match=r"shadowsim\[viz\]"):
        _result().plot_results()


@pytest.mark.viz
def test_plot_results_draws_one_curve_per_label(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt

    plotted: list[str] = []
    titled: list[str] = []
    shown = {"called": False}

    def spy_plot(_times: object, _trace: object, *, label: str) -> None:
        plotted.append(label)

    monkeypatch.setattr(plt, "plot", spy_plot)
    monkeypatch.setattr(plt, "title", titled.append)
    monkeypatch.setattr(plt, "xlabel", lambda _label: None)
    monkeypatch.setattr(plt, "ylabel", lambda _label: None)
    monkeypatch.setattr(plt, "legend", lambda: None)
    monkeypatch.setattr(plt, "show", lambda: shown.__setitem__("called", True))

    result = _result()
    result.plot_results(title="shadow")
    assert plotted == ["P_0", "P_1"]
    assert titled == ["shadow"]
    assert shown["called"]

    plotted.clear()
    result.plot_results()
    assert plotted == ["P_0", "P_1"]
    assert titled == ["shadow"]


def test_shadow_observable_fields_default_empty_and_are_not_saved(tmp_path: Path) -> None:
    assert _result().shadow_observable_expectations == []
    assert _result().shadow_observable_labels == []

    source = _result(
        shadow_observable_expectations=[np.array([0.1, 0.2, 0.3])],
        shadow_observable_labels=["P_0"],
    )
    out = source.save(tmp_path / "with_extras")
    assert sorted(path.name for path in out.iterdir()) == ["expectations.npy", "meta.json", "times.npy"]
    assert "shadow_observable_labels" not in json.loads((out / "meta.json").read_text(encoding="utf-8"))

    loaded = ShadowSimulationResult.load(out)
    assert loaded.shadow_observable_expectations == []
    assert loaded.shadow_observable_labels == []


@pytest.mark.qiskit
def test_padded_shadow_run_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("qiskit")
    from shadowsim.backends.numpy import NumpyCircuitBackend

    result = run_shadow_simulation(
        Hamiltonian("Z"),
        OperatorSet(["X", "Y", "Z"]),
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        total_time=0.5,
        time_steps=5,
        circuit_backend=NumpyCircuitBackend(),
    )
    assert result.shadow_hamiltonian is not None
    assert result.basis == ["X", "Y", "Z"]
    assert result.basis == list(result.shadow_hamiltonian.basis)
    assert result.h_s_dimension == 3
    assert result.h_s_dimension == int(result.shadow_hamiltonian.H_S.shape[0])
    assert result.shadow_num_qubits == 2
    assert result.H_S_padded is not None
    assert result.H_S_padded.shape == (4, 4)
    assert len(result.expectations) > 1

    loaded = ShadowSimulationResult.load(result.save(tmp_path / "padded"))
    assert loaded.shadow_hamiltonian is None
    assert loaded.shadow_state is None
    assert loaded.H_S_padded is None
    assert loaded.basis == result.basis
    assert loaded.labels == result.labels
    assert loaded.shadow_num_qubits == 2
    assert loaded.h_s_dimension == 3
    assert np.allclose(loaded.times, result.times)
    for loaded_curve, source_curve in zip(loaded.expectations, result.expectations, strict=True):
        assert np.allclose(loaded_curve, source_curve)
