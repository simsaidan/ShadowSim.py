from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from src.simulators.simulator import Simulator


class Benchmark:

    def __init__(self, simulator_a: Simulator, simulator_b: Simulator):
        if not np.array_equal(simulator_a.tlist, simulator_b.tlist):
            raise ValueError("simulators must use the same time grid (tlist)")
        self.simulator_a = simulator_a
        self.simulator_b = simulator_b

    def get_tlist(self) -> np.ndarray:
        return self.simulator_a.tlist

    def run(self):
        self.simulator_a.run()
        self.simulator_b.run()

    def get_results(self, index: int = None):
        return self.simulator_a.get_results(index), self.simulator_b.get_results(index)

    def save_result_plot(
        self,
        indices: list[int] | None = None,
        *,
        dpi: float = 150,
        labels: list[str] | None = None,
        title_a: str | None = None,
        title_b: str | None = None,
        title: str | None = None,
    ) -> tuple[Path, Path, Path]:
        pa = self.simulator_a.save_result_plot(
            indices=indices, dpi=dpi, labels=labels, title=title_a
        )
        pb = self.simulator_b.save_result_plot(
            indices=indices, dpi=dpi, labels=labels, title=title_b
        )
        pdiff = self._save_abs_diff_plot(
            indices=indices, dpi=dpi, title=title, labels=labels
        )
        return pa, pb, pdiff

    def _save_abs_diff_plot(
        self,
        indices: list[int] | None,
        *,
        dpi: float,
        title: str | None,
        labels: list[str] | None = None,
    ) -> Path:
        ra = self.simulator_a.results
        rb = self.simulator_b.results
        if ra is None or rb is None:
            raise ValueError(
                "Results are not available. Call run() (or simulate both) before save()."
            )
        if len(ra) != len(rb):
            raise ValueError(f"Mismatched observable counts: {len(ra)} vs {len(rb)}")
        if indices is None:
            indices = list(range(len(ra)))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = Path("results") / f"benchmark_abs_diff_{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots()
        try:
            t = self.simulator_a.tlist
            for plot_i, index in enumerate(indices):
                curve_label = (
                    labels[plot_i]
                    if labels is not None and plot_i < len(labels)
                    else str(index)
                )
                diff = np.abs(np.asarray(ra[index]) - np.asarray(rb[index]))
                ax.plot(t, diff, label=curve_label)
            ax.set_xlabel("Time")
            ax.set_ylabel("|expectation A − expectation B|")
            if title:
                ax.set_title(title)
            ax.legend()
            fig.savefig(path, dpi=dpi, bbox_inches="tight")
        finally:
            plt.close(fig)
        return path

    def __str__(self):
        return (
            "Benchmark("
            f"simulator_a={self.simulator_a.__class__.__name__}, "
            f"simulator_b={self.simulator_b.__class__.__name__}"
            ")"
        )

    def __repr__(self):
        return (
            "Benchmark("
            f"simulator_a={self.simulator_a!r}, "
            f"simulator_b={self.simulator_b!r}"
            ")"
        )
