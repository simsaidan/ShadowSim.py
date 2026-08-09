from pathlib import Path

import numpy as np
import pytest

from shadowsim.benchmarking import Benchmark
from shadowsim.core import Hamiltonian
from shadowsim.core import State
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


def test_benchmark_rejects_mismatched_tlist():
    a = StubSimulator(time_steps=3)
    b = StubSimulator(time_steps=4)
    with pytest.raises(ValueError, match="same time grid"):
        Benchmark(a, b)


def test_benchmark_run_and_get_results():
    a, b = _pair()
    benchmark = Benchmark(a, b)

    assert np.array_equal(benchmark.get_tlist(), a.tlist)

    benchmark.run()
    all_a, all_b = benchmark.get_results()
    assert len(all_a) == len(all_b) == 2
    assert np.allclose(all_a[0], a.get_results(0))
    assert np.allclose(all_b[1], b.get_results(1))

    first_a, first_b = benchmark.get_results(0)
    assert np.allclose(first_a, a.get_results(0))
    assert np.allclose(first_b, b.get_results(0))


def test_benchmark_save_result_plot_writes_three_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = _pair()
    # Distinct curves so the abs-diff plot is nontrivial.
    b._curves = [np.cos(b.tlist) + 0.1, np.sin(b.tlist) - 0.1]
    benchmark = Benchmark(a, b)
    benchmark.run()

    pa, pb, pdiff = benchmark.save_result_plot(
        labels=["cavity", "emitter"],
        title_a="A",
        title_b="B",
        title="diff",
        dpi=80,
    )

    assert pa.is_file()
    assert pb.is_file()
    assert pdiff.is_file()
    assert pa.parent == Path("results")
    assert pdiff.name.startswith("benchmark_abs_diff_")


def test_benchmark_abs_diff_requires_results():
    a, b = _pair()
    benchmark = Benchmark(a, b)
    with pytest.raises(ValueError, match="Results are not available"):
        benchmark._save_abs_diff_plot(indices=None, dpi=80, title=None)


def test_benchmark_abs_diff_with_explicit_indices_and_no_title(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = _pair()
    a.results = a._curves
    b.results = b._curves
    benchmark = Benchmark(a, b)

    path = benchmark._save_abs_diff_plot(indices=[0], dpi=80, title=None)
    assert path.is_file()


def test_benchmark_abs_diff_rejects_mismatched_observable_counts():
    a = StubSimulator(id="a", curves=[np.zeros(3), np.ones(3)])
    b = StubSimulator(id="b", curves=[np.zeros(3)])
    a.results = a._curves
    b.results = b._curves
    benchmark = Benchmark(a, b)

    with pytest.raises(ValueError, match="Mismatched observable counts"):
        benchmark._save_abs_diff_plot(indices=None, dpi=80, title=None)


def test_benchmark_str_and_repr():
    a, b = _pair()
    benchmark = Benchmark(a, b)

    assert str(benchmark) == "Benchmark(simulator_a=StubSimulator, simulator_b=StubSimulator)"
    assert "StubSimulator(" in repr(benchmark)
