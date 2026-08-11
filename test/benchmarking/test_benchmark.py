from pathlib import Path

import numpy as np
import pytest

from shadowsim.benchmarking import Benchmark
from shadowsim.core import Hamiltonian, State
from shadowsim.simulators.simulator import Simulator

Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


class StubSimulator(Simulator):
    """Minimal simulator with canned expectation traces."""

    def __init__(
        self,
        *,
        total_time: float = 1.0,
        time_steps: int = 3,
        curves: list[np.ndarray] | None = None,
        id: str = "stub",
    ):
        super().__init__(
            [Hamiltonian(Z)],
            [],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            1,
            total_time,
            time_steps,
            id,
        )
        if curves is None:
            t = self.tlist
            curves = [np.cos(t), np.sin(t)]
        self._curves = [np.asarray(c, dtype=float) for c in curves]

    def simulate(self):
        self.results = list(self._curves)
        return self.results


def _pair(**kwargs):
    return StubSimulator(id="a", **kwargs), StubSimulator(id="b", **kwargs)


def test_benchmark_rejects_no_challengers():
    a = StubSimulator(id="a")
    with pytest.raises(ValueError, match="at least one challenger"):
        Benchmark(a)


def test_benchmark_rejects_mismatched_tlist():
    a = StubSimulator(time_steps=3)
    b = StubSimulator(time_steps=4)
    with pytest.raises(ValueError, match="same time grid"):
        Benchmark(a, b)


def test_benchmark_rejects_mismatched_tlist_among_challengers():
    ref = StubSimulator(id="ref", time_steps=3)
    c1 = StubSimulator(id="c1", time_steps=3)
    c2 = StubSimulator(id="c2", time_steps=4)
    with pytest.raises(ValueError, match="same time grid"):
        Benchmark(ref, c1, c2)


def test_benchmark_run_and_get_results():
    a, b = _pair()
    benchmark = Benchmark(a, b)

    assert np.array_equal(benchmark.get_tlist(), a.tlist)
    assert benchmark.simulators == [a, b]

    benchmark.run()
    all_results = benchmark.get_results()
    assert len(all_results) == 2
    assert np.allclose(all_results[0][0], a.get_results(0))
    assert np.allclose(all_results[1][1], b.get_results(1))

    first_results = benchmark.get_results(0)
    assert np.allclose(first_results[0], a.get_results(0))
    assert np.allclose(first_results[1], b.get_results(0))


def test_benchmark_run_and_get_results_three_simulators():
    ref = StubSimulator(id="ref")
    c1 = StubSimulator(id="c1")
    c2 = StubSimulator(id="c2")
    c1._curves = [np.cos(c1.tlist) + 0.1, np.sin(c1.tlist) - 0.1]
    c2._curves = [np.cos(c2.tlist) + 0.2, np.sin(c2.tlist) - 0.2]
    benchmark = Benchmark(ref, c1, c2)

    assert benchmark.simulators == [ref, c1, c2]
    benchmark.run()
    all_results = benchmark.get_results()
    assert len(all_results) == 3
    assert np.allclose(all_results[0][0], ref.get_results(0))
    assert np.allclose(all_results[1][0], c1.get_results(0))
    assert np.allclose(all_results[2][1], c2.get_results(1))

    first_results = benchmark.get_results(0)
    assert len(first_results) == 3
    assert np.allclose(first_results[2], c2.get_results(0))


def test_benchmark_save_result_plot_writes_three_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = _pair()
    # Distinct curves so the abs-diff plot is nontrivial.
    b._curves = [np.cos(b.tlist) + 0.1, np.sin(b.tlist) - 0.1]
    benchmark = Benchmark(a, b)
    benchmark.run()

    paths = benchmark.save_result_plot(
        labels=["cavity", "emitter"],
        titles=["A", "B"],
        title="diff",
        dpi=80,
    )

    assert len(paths) == 3
    pa, pb, pdiff = paths
    assert pa.is_file()
    assert pb.is_file()
    assert pdiff.is_file()
    assert pa.parent == Path("results")
    assert pdiff.name.startswith("benchmark_abs_diff_b_")


def test_benchmark_save_result_plot_writes_five_files_for_three_sims(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ref = StubSimulator(id="ref")
    c1 = StubSimulator(id="c1")
    c2 = StubSimulator(id="c2")
    c1._curves = [np.cos(c1.tlist) + 0.1, np.sin(c1.tlist) - 0.1]
    c2._curves = [np.cos(c2.tlist) + 0.2, np.sin(c2.tlist) - 0.2]
    benchmark = Benchmark(ref, c1, c2)
    benchmark.run()

    paths = benchmark.save_result_plot(
        labels=["cavity", "emitter"],
        titles=["Ref", "C1", "C2"],
        title="diff",
        dpi=80,
    )

    assert len(paths) == 5
    for path in paths:
        assert path.is_file()
    assert paths[3].name.startswith("benchmark_abs_diff_c1_")
    assert paths[4].name.startswith("benchmark_abs_diff_c2_")


def test_benchmark_abs_diff_requires_results():
    a, b = _pair()
    benchmark = Benchmark(a, b)
    with pytest.raises(ValueError, match="Results are not available"):
        benchmark._save_abs_diff_plot(b, indices=None, dpi=80, title=None)


def test_benchmark_abs_diff_with_explicit_indices_and_no_title(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = _pair()
    a.results = a._curves
    b.results = b._curves
    benchmark = Benchmark(a, b)

    path = benchmark._save_abs_diff_plot(b, indices=[0], dpi=80, title=None)
    assert path.is_file()
    assert path.name.startswith("benchmark_abs_diff_b_")


def test_benchmark_abs_diff_rejects_mismatched_observable_counts():
    a = StubSimulator(id="a", curves=[np.zeros(3), np.ones(3)])
    b = StubSimulator(id="b", curves=[np.zeros(3)])
    a.results = a._curves
    b.results = b._curves
    benchmark = Benchmark(a, b)

    with pytest.raises(ValueError, match="Mismatched observable counts"):
        benchmark._save_abs_diff_plot(b, indices=None, dpi=80, title=None)


def test_benchmark_str_and_repr():
    a, b = _pair()
    benchmark = Benchmark(a, b)

    assert str(benchmark) == "Benchmark(reference=StubSimulator, challengers=[StubSimulator])"
    assert "reference=" in repr(benchmark)
    assert "challengers=" in repr(benchmark)
    assert "StubSimulator(" in repr(benchmark)
