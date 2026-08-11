"""Compare results from a reference simulator against one or more challengers."""

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from shadowsim.simulators.simulator import Simulator


class Benchmark:
    """Compare expectation traces from a reference and challenger simulators."""

    def __init__(self, reference: Simulator, *challengers: Simulator):
        """Initialize a Benchmark for simulators on the same time grid."""
        if not challengers:
            raise ValueError("at least one challenger is required")
        for challenger in challengers:
            if not np.array_equal(reference.tlist, challenger.tlist):
                raise ValueError("simulators must use the same time grid (tlist)")
        self.reference = reference
        self.challengers = list(challengers)

    @property
    def simulators(self) -> list[Simulator]:
        """Return the reference followed by all challengers."""
        return [self.reference, *self.challengers]

    def get_tlist(self) -> np.ndarray:
        """Return the shared simulation time grid."""
        return self.reference.tlist

    def run(self):
        """Run the reference and all challenger simulators."""
        for simulator in self.simulators:
            simulator.run()

    def get_results(self, index: int = None):
        """Return matching result traces from the reference and each challenger."""
        return [simulator.get_results(index) for simulator in self.simulators]

    def save_result_plot(
        self,
        indices: list[int] | None = None,
        *,
        dpi: float = 150,
        labels: list[str] | None = None,
        titles: list[str] | None = None,
        title: str | None = None,
    ) -> list[Path]:
        """Save plots for each simulator and abs-diff vs the reference.

        Returns ``[ref_plot, *challenger_plots, *diff_plots]``.
        """
        paths: list[Path] = []
        for i, simulator in enumerate(self.simulators):
            sim_title = titles[i] if titles is not None and i < len(titles) else None
            paths.append(simulator.save_result_plot(indices=indices, dpi=dpi, labels=labels, title=sim_title))
        for challenger in self.challengers:
            paths.append(
                self._save_abs_diff_plot(
                    challenger,
                    indices=indices,
                    dpi=dpi,
                    title=title,
                    labels=labels,
                )
            )
        return paths

    def _save_abs_diff_plot(
        self,
        challenger: Simulator,
        indices: list[int] | None,
        *,
        dpi: float,
        title: str | None,
        labels: list[str] | None = None,
    ) -> Path:
        ra = self.reference.results
        rb = challenger.results
        if ra is None or rb is None:
            raise ValueError("Results are not available. Call run() (or simulate all) before save().")
        if len(ra) != len(rb):
            raise ValueError(f"Mismatched observable counts: {len(ra)} vs {len(rb)}")
        if indices is None:
            indices = list(range(len(ra)))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        challenger_id = challenger.id
        path = Path("results") / f"benchmark_abs_diff_{challenger_id}_{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots()
        try:
            t = self.reference.tlist
            for plot_i, index in enumerate(indices):
                curve_label = labels[plot_i] if labels is not None and plot_i < len(labels) else str(index)
                diff = np.abs(np.asarray(ra[index]) - np.asarray(rb[index]))
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

    def __str__(self):
        """Return a string representation of the Benchmark."""
        challenger_names = ", ".join(c.__class__.__name__ for c in self.challengers)
        return f"Benchmark(reference={self.reference.__class__.__name__}, challengers=[{challenger_names}])"

    def __repr__(self):
        """Return a string representation of the Benchmark."""
        return f"Benchmark(reference={self.reference!r}, challengers={self.challengers!r})"
