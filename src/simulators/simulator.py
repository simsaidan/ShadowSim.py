from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from src.core.hamiltonian import Hamiltonian
from src.core.state import State
from src.core.operator_set import Operator


class Simulator:
    def __init__(
        self,
        hamiltonians: list[Hamiltonian],
        lindblads: list[Operator],
        initial_state: State,
        num_qubits: int,
        total_time: float,
        time_steps: int,
        id: str,
    ):
        if not hamiltonians:
            raise ValueError("hamiltonians must be a non-empty list")
        self.hamiltonians = list(hamiltonians)
        self.lindblads = list(lindblads)
        self.initial_state = initial_state
        self.num_qubits = num_qubits
        self.total_time = total_time
        self.time_steps = time_steps
        self.id = id
        self.results = None
        self.tlist = np.linspace(0, self.total_time, self.time_steps)

    def run(self):
        return self.simulate()

    def simulate(self):
        raise NotImplementedError("Subclasses must implement simulate()")

    def get_results(self, index: int = None):
        if self.results is None:
            raise ValueError(
                "Results are not available. Please run the simulation first."
            )
        if index is None:
            return self.results
        return self.results[index]

    def plot_results(
        self,
        indices: list[int] | None = None,
        *,
        labels: list[str] | None = None,
        title: str | None = None,
    ):
        if indices is None:
            indices = list(range(len(self.results)))
        for plot_i, index in enumerate(indices):
            curve_label = (
                labels[plot_i]
                if labels is not None and plot_i < len(labels)
                else str(index)
            )
            plt.plot(self.tlist, self.get_results(index), label=curve_label)
        if title:
            plt.title(title)
        plt.xlabel("Time")
        plt.ylabel("Expectation")
        plt.legend()
        plt.show()

    def save_result_plot(
        self,
        indices: list[int] | None = None,
        *,
        dpi: float = 150,
        labels: list[str] | None = None,
        title: str | None = None,
    ) -> Path:
        """
        Plot expectation traces vs `tlist` and save under ``results/`` as
        ``{id}_{timestamp}.png`` (``id`` is set per simulator subclass). Does not
        open an interactive window.
        """
        if indices is None:
            indices = list(range(len(self.results)))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = Path("results") / f"{self.id}_{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots()
        try:
            for plot_i, index in enumerate(indices):
                curve_label = (
                    labels[plot_i]
                    if labels is not None and plot_i < len(labels)
                    else str(index)
                )
                ax.plot(
                    self.tlist,
                    self.get_results(index),
                    label=curve_label,
                )
            ax.set_xlabel("Time")
            ax.set_ylabel("Expectation")
            if title:
                ax.set_title(title)
            ax.legend()
            fig.savefig(path, dpi=dpi, bbox_inches="tight")
        finally:
            plt.close(fig)
        return path

    def __str__(self):
        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"num_qubits={self.num_qubits}, "
            f"time_steps={self.time_steps}"
            ")"
        )

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"hamiltonians={self.hamiltonians!r}, "
            f"lindblads={self.lindblads!r}, "
            f"initial_state={self.initial_state!r}, "
            f"num_qubits={self.num_qubits}, "
            f"total_time={self.total_time}, "
            f"time_steps={self.time_steps}, "
            f"id={self.id!r}"
            ")"
        )
