"""Structured simulation result with metadata and serialize/reload."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np


def package_version() -> str:
    """Return the installed ``shadowsim`` version, or ``"unknown"`` if unavailable."""
    try:
        return version("shadowsim")
    except PackageNotFoundError:
        return "unknown"


def _as_float_array(values: Sequence[float] | np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def _observables_to_npy(observables: Sequence[np.ndarray]) -> np.ndarray:
    """Pack expectation traces for ``np.save``.

    Equal-length real traces become a stacked 2D ``float64`` array. Otherwise an
    object array of 1D arrays is used so jagged shapes round-trip.
    """
    arrays = [_as_float_array(obs) for obs in observables]
    if not arrays:
        return np.empty((0, 0), dtype=np.float64)
    if all(a.ndim == 1 and a.shape == arrays[0].shape for a in arrays):
        return np.stack(arrays, axis=0)
    packed = np.empty(len(arrays), dtype=object)
    for i, arr in enumerate(arrays):
        packed[i] = arr
    return packed


def _observables_from_npy(raw: np.ndarray) -> list[np.ndarray]:
    if raw.dtype == object:
        return [_as_float_array(item) for item in raw.tolist()]
    if raw.ndim == 0:
        return [_as_float_array(raw)]
    if raw.ndim == 1:
        return [_as_float_array(raw)]
    return [_as_float_array(row) for row in raw]


def _states_to_npy(states: Sequence[np.ndarray]) -> np.ndarray:
    packed = np.empty(len(states), dtype=object)
    for i, state in enumerate(states):
        packed[i] = np.asarray(state)
    return packed


def _states_from_npy(raw: np.ndarray) -> list[np.ndarray]:
    if raw.dtype == object:
        return [np.asarray(item) for item in raw.tolist()]
    return [np.asarray(raw)]


@dataclass(frozen=True)
class SimulationResult:
    """Outputs from a simulator ``simulate()`` / ``run()`` call.

    Attributes:
        times: Simulation time grid.
        observables: One expectation trajectory per measured observable / group.
        states: Optional state trajectory (``None`` when the backend does not store states).
        seed: Random seed used for the run, if any.
        algorithm: Backend identifier (typically the simulator ``id``).
        runtime: Wall-clock seconds for the ``simulate()`` call, if recorded.
        metadata: Reproducibility and parameter metadata (version, params, …).
    """

    times: np.ndarray
    observables: list[np.ndarray]
    states: list[np.ndarray] | None = None
    seed: int | None = None
    algorithm: str = ""
    runtime: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def save(self, path: str | Path) -> Path:
        """Write this result to a directory as NumPy arrays plus ``meta.json``.

        Layout::

            path/
              times.npy
              observables.npy
              states.npy   # only when ``states`` is not None
              meta.json
        """
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "times.npy", np.asarray(self.times))
        np.save(out / "observables.npy", _observables_to_npy(self.observables), allow_pickle=True)
        if self.states is not None:
            np.save(out / "states.npy", _states_to_npy(self.states), allow_pickle=True)
        meta = {
            "seed": self.seed,
            "algorithm": self.algorithm,
            "runtime": self.runtime,
            "metadata": self.metadata,
            "has_states": self.states is not None,
        }
        (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: str | Path) -> SimulationResult:
        """Reload a result previously written by :meth:`save`."""
        root = Path(path)
        if not root.is_dir():
            raise FileNotFoundError(f"SimulationResult directory not found: {root}")
        meta_path = root / "meta.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"missing meta.json in {root}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        times = np.load(root / "times.npy")
        observables = _observables_from_npy(np.load(root / "observables.npy", allow_pickle=True))
        states: list[np.ndarray] | None = None
        if meta.get("has_states", False):
            states_path = root / "states.npy"
            if not states_path.is_file():
                raise FileNotFoundError(f"meta.json claims states but {states_path} is missing")
            states = _states_from_npy(np.load(states_path, allow_pickle=True))
        return cls(
            times=times,
            observables=observables,
            states=states,
            seed=meta.get("seed"),
            algorithm=str(meta.get("algorithm", "")),
            runtime=meta.get("runtime"),
            metadata=dict(meta.get("metadata") or {}),
        )
