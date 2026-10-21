"""Compare results from a reference simulator against one or more challengers."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from shadowsim._optional import import_optional
from shadowsim.simulators.simulator import Simulator, _Trace, _Traces


def _report_ids(simulators: list[Simulator]) -> list[str]:
    """Return one id per simulator, suffixing duplicates in list order.

    An id used once is unchanged. An id used more than once is reported as
    ``id#1``, ``id#2``, and so on, counting from the start of ``simulators``.
    """
    counts: dict[str, int] = {}
    for simulator in simulators:
        counts[simulator.id] = counts.get(simulator.id, 0) + 1
    seen: dict[str, int] = {}
    labels: list[str] = []
    for simulator in simulators:
        if counts[simulator.id] == 1:
            labels.append(simulator.id)
            continue
        seen[simulator.id] = seen.get(simulator.id, 0) + 1
        labels.append(f"{simulator.id}#{seen[simulator.id]}")
    return labels


class Benchmark:
    """Compare expectation traces from a reference and challenger simulators."""

    def __init__(self, reference: Simulator, *challengers: Simulator) -> None:
        """Initialize a Benchmark for simulators on the same time grid."""
        if not challengers:
            raise ValueError("at least one challenger is required")
        for challenger in challengers:
            if not np.array_equal(reference.tlist, challenger.tlist):
                raise ValueError("simulators must use the same time grid (tlist)")
        self.reference = reference
        self.challengers = list(challengers)
        self._wall_times: list[float] = []

    @property
    def simulators(self) -> list[Simulator]:
        """Return the reference followed by all challengers."""
        return [self.reference, *self.challengers]

    def get_tlist(self) -> npt.NDArray[np.float64]:
        """Return the shared simulation time grid."""
        return self.reference.tlist

    def run(self) -> None:
        """Run the reference and all challenger simulators."""
        times: list[float] = []
        for simulator in self.simulators:
            start = time.perf_counter()
            simulator.run()
            times.append(time.perf_counter() - start)
        self._wall_times = times

    def get_results(self, index: int | None = None) -> list[_Traces | _Trace]:
        """Return matching result traces from the reference and each challenger."""
        return [simulator.get_results(index) for simulator in self.simulators]

    def error_metrics(self, indices: list[int] | None = None) -> list[dict[str, Any]]:
        """Return L∞ / L2 / MAE / RMSE vs reference for each challenger.

        For each selected observable, with error series ``e = y_ref − y_challenger``:

        - ``linf``: ``max |e|``
        - ``l2``: Euclidean norm ``||e||_2``
        - ``mae``: ``mean(|e|)``
        - ``rmse``: ``sqrt(mean(e²))``

        ``challenger_id`` is that simulator's id. When the same id appears more
        than once in the benchmark, it is reported as ``id#1``, ``id#2``, and so
        on, counting the reference and challengers in order.
        """
        metrics: list[dict[str, Any]] = []
        labels = _report_ids(self.simulators)
        for challenger, label in zip(self.challengers, labels[1:], strict=True):
            ra, rb = self._matching_results(challenger)
            selected = list(range(len(ra))) if indices is None else indices
            observables = []
            for index in selected:
                err = self._diff_series(ra[index], rb[index])
                observables.append(
                    {
                        "index": index,
                        "linf": float(np.max(np.abs(err))),
                        "l2": float(np.linalg.norm(err)),
                        "mae": float(np.mean(np.abs(err))),
                        "rmse": float(np.sqrt(np.mean(err**2))),
                    }
                )
            metrics.append({"challenger_id": label, "observables": observables})
        return metrics

    def resource_metrics(self) -> list[dict[str, Any]]:
        """Return wall-clock time and shot budget for each simulator.

        Requires ``run()`` first. Shot fields are ``None`` when a simulator has no
        ``shots`` attribute (e.g. QuTiP); otherwise ``num_jobs`` is ``len(tlist)``
        and ``total_shots`` is ``shots_per_job * num_jobs``.

        ``simulator_id`` is that simulator's id. When the same id appears more
        than once, it is reported as ``id#1``, ``id#2``, and so on, in benchmark
        order. Each row keeps the wall time of that run.
        """
        if len(self._wall_times) != len(self.simulators):
            raise ValueError("Results are not available. Call run() (or simulate all) before save().")
        metrics: list[dict[str, Any]] = []
        labels = _report_ids(self.simulators)
        for simulator, wall_time, label in zip(self.simulators, self._wall_times, labels, strict=True):
            shots_per_job = getattr(simulator, "shots", None)
            if shots_per_job is None:
                num_jobs = None
                total_shots = None
            else:
                num_jobs = len(simulator.tlist)
                total_shots = shots_per_job * num_jobs
            metrics.append(
                {
                    "simulator_id": label,
                    "wall_time_s": wall_time,
                    "shots_per_job": shots_per_job,
                    "num_jobs": num_jobs,
                    "total_shots": total_shots,
                }
            )
        return metrics

    def save_error_metrics(
        self,
        indices: list[int] | None = None,
        *,
        path: Path | None = None,
        output_dir: str | Path = "results",
    ) -> Path:
        """Write error and resource metrics to JSON.

        When ``path`` is set, that file is written and ``output_dir`` is ignored.
        Otherwise the timestamped JSON is written under ``output_dir`` (default
        ``results/``), which is created if it does not exist.

        Payload shape: ``{"errors": error_metrics(...), "resources": resource_metrics()}``.
        """
        if path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = Path(output_dir) / f"benchmark_error_metrics_{stamp}.json"
        else:
            path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "errors": self.error_metrics(indices),
            "resources": self.resource_metrics(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path

    def save_result_plot(
        self,
        indices: list[int] | None = None,
        *,
        dpi: float = 150,
        labels: list[str] | None = None,
        titles: list[str] | None = None,
        title: str | None = None,
        output_dir: str | Path = "results",
    ) -> list[Path]:
        """Save plots for each simulator and abs-diff vs the reference.

        Every file from this call is written under ``output_dir`` (default
        ``results/``), which is created if it does not exist.
        Returns ``[ref_plot, *challenger_plots, *diff_plots]``.
        """
        paths: list[Path] = []
        for i, simulator in enumerate(self.simulators):
            sim_title = titles[i] if titles is not None and i < len(titles) else None
            paths.append(
                simulator.save_result_plot(
                    indices=indices,
                    dpi=dpi,
                    labels=labels,
                    title=sim_title,
                    output_dir=output_dir,
                )
            )
        for challenger in self.challengers:
            paths.append(
                self._save_abs_diff_plot(
                    challenger,
                    indices=indices,
                    dpi=dpi,
                    title=title,
                    labels=labels,
                    output_dir=output_dir,
                )
            )
        return paths

    def _matching_results(self, challenger: Simulator) -> tuple[_Traces, _Traces]:
        """Return ``(ref_results, challenger_results)`` or raise if unavailable/mismatched."""
        ra = self.reference.results
        rb = challenger.results
        if ra is None or rb is None:
            raise ValueError("Results are not available. Call run() (or simulate all) before save().")
        if len(ra) != len(rb):
            raise ValueError(f"Mismatched observable counts: {len(ra)} vs {len(rb)}")
        return ra, rb

    @staticmethod
    def _diff_series(ref_curve: _Trace, challenger_curve: _Trace) -> npt.NDArray[np.float64]:
        """Return ``y_ref − y_challenger`` as a float array."""
        return np.asarray(ref_curve, dtype=float) - np.asarray(challenger_curve, dtype=float)

    def _save_abs_diff_plot(
        self,
        challenger: Simulator,
        indices: list[int] | None,
        *,
        dpi: float,
        title: str | None,
        labels: list[str] | None = None,
        output_dir: str | Path = "results",
    ) -> Path:
        ra, rb = self._matching_results(challenger)
        plt = import_optional("matplotlib.pyplot", extra="viz")
        if indices is None:
            indices = list(range(len(ra)))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        challenger_id = challenger.id
        path = Path(output_dir) / f"benchmark_abs_diff_{challenger_id}_{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots()
        try:
            t = self.reference.tlist
            for plot_i, index in enumerate(indices):
                curve_label = labels[plot_i] if labels is not None and plot_i < len(labels) else str(index)
                diff = np.abs(self._diff_series(ra[index], rb[index]))
                ax.plot(t, diff, label=curve_label)
            ax.set_xlabel("Time")
            ax.set_ylabel(f"|expectation ref − expectation {challenger_id}|")
            if title:
                ax.set_title(title)
            ax.legend()
            fig.savefig(path, dpi=dpi, bbox_inches="tight")
        finally:
            plt.close(fig)
        return path

    def __str__(self) -> str:
        """Return a string representation of the Benchmark."""
        challenger_names = ", ".join(c.__class__.__name__ for c in self.challengers)
        return f"Benchmark(reference={self.reference.__class__.__name__}, challengers=[{challenger_names}])"

    def __repr__(self) -> str:
        """Return a string representation of the Benchmark."""
        return f"Benchmark(reference={self.reference!r}, challengers={self.challengers!r})"
