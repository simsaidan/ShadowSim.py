"""Structured simulation result with metadata and serialize/reload."""

import json
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from numpy.lib.npyio import NpzFile

# Real, integer, and complex arrays. Object arrays are excluded: NumPy stores
# them as pickles, and unpickling runs the payload.
_NUMERIC_KINDS = frozenset("biufc")


def package_version() -> str:
    """Return the installed ``shadowsim`` version, or ``"unknown"`` if unavailable."""
    try:
        return version("shadowsim")
    except PackageNotFoundError:
        return "unknown"


def _as_float_array(values: Sequence[float] | np.ndarray) -> npt.NDArray[np.float64]:
    return np.asarray(values, dtype=np.float64)


def _numeric_array(values: np.ndarray, label: str) -> np.ndarray:
    """Return ``values`` when it can be stored without pickle."""
    array = np.asarray(values)
    if array.dtype.hasobject or array.dtype.kind not in _NUMERIC_KINDS:
        raise ValueError(f"{label} must be a numeric array, got dtype {array.dtype}")
    return array


def _write_archive(path: Path, arrays: Sequence[np.ndarray]) -> None:
    """Write numeric arrays to ``path`` as ``arr0``, ``arr1``, ...

    One entry per array keeps jagged shapes. Each entry is saved with
    ``allow_pickle=False``. ``np.savez`` is not given that keyword: NumPy 2.0
    stores it as an array named ``allow_pickle``.
    """
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for index, array in enumerate(arrays):
            numeric = _numeric_array(array, f"{path.name} entry {index}")
            buffer = BytesIO()
            np.save(buffer, numeric, allow_pickle=False)
            archive.writestr(f"arr{index}.npy", buffer.getvalue())


def _is_pickle_refusal(exc: BaseException) -> bool:
    return "pickle" in str(exc).lower()


def _read_array_file(path: Path) -> np.ndarray | NpzFile:
    """Load ``path`` with ``allow_pickle=False``.

    Raises:
        ValueError: If NumPy refuses the file because it contains a pickle.
            The payload is not executed.
    """
    try:
        return np.load(path, allow_pickle=False)
    except ValueError as exc:
        if _is_pickle_refusal(exc):
            raise ValueError(f"{path.name} contains a pickle payload and was not loaded") from exc
        raise


def _read_npy(path: Path) -> np.ndarray:
    loaded = _read_array_file(path)
    if isinstance(loaded, np.ndarray):
        return np.array(loaded, copy=True)
    loaded.close()
    raise ValueError(f"expected an array in {path}")


def _array_index(name: str) -> int | None:
    prefix = "arr"
    if not name.startswith(prefix):
        return None
    suffix = name[len(prefix) :]
    if not suffix.isascii() or not suffix.isdigit():
        return None
    return int(suffix)


def _ordered_archive_names(names: Sequence[str], path: Path) -> list[str]:
    indexed: list[tuple[int, str]] = []
    for name in names:
        index = _array_index(name)
        if index is None:
            raise ValueError(f"unexpected array {name!r} in {path.name}")
        indexed.append((index, name))
    indexed.sort()
    indexes = [index for index, _name in indexed]
    if indexes != list(range(len(indexes))):
        raise ValueError(f"{path.name} is missing an array or contains a duplicate name")
    return [name for _index, name in indexed]


def _read_archive(path: Path) -> list[np.ndarray]:
    loaded = _read_array_file(path)
    if isinstance(loaded, np.ndarray):
        raise ValueError(f"expected an array archive at {path}")
    with loaded:
        names = _ordered_archive_names(loaded.files, path)
        try:
            arrays = [np.array(loaded[name], copy=True) for name in names]
        except ValueError as exc:
            if _is_pickle_refusal(exc):
                raise ValueError(f"{path.name} contains a pickle payload and was not loaded") from exc
            raise
    return [_numeric_array(array, f"{path.name} entry {index}") for index, array in enumerate(arrays)]


def _observables_from_npy(raw: np.ndarray) -> list[npt.NDArray[np.float64]]:
    """Read a numeric ``observables.npy`` written by an older version.

    A stacked 2D array is one trace per row. A 1D array and a scalar are one trace.
    """
    if raw.ndim == 0:
        return [_as_float_array(raw)]
    if raw.ndim == 1:
        return [_as_float_array(raw)]
    return [_as_float_array(row) for row in raw]


def _load_observables(root: Path) -> list[npt.NDArray[np.float64]]:
    archive = root / "observables.npz"
    if archive.is_file():
        return [_as_float_array(array) for array in _read_archive(archive)]
    legacy = root / "observables.npy"
    if legacy.is_file():
        return _observables_from_npy(_read_npy(legacy))
    raise FileNotFoundError(f"missing observables.npz in {root}")


def _load_states(root: Path) -> list[np.ndarray]:
    archive = root / "states.npz"
    if archive.is_file():
        return _read_archive(archive)
    if (root / "states.npy").is_file():
        raise ValueError(f"states.npy is an older object-array format; re-save states as a numeric {archive.name}")
    raise FileNotFoundError(f"meta.json claims states but {archive} is missing")


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

    times: npt.NDArray[np.float64]
    observables: list[npt.NDArray[np.float64]]
    states: list[np.ndarray] | None = None
    seed: int | None = None
    algorithm: str = ""
    runtime: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def save(self, path: str | Path) -> Path:
        """Write this result to a directory as numeric arrays plus ``meta.json``.

        Layout::

            path/
              times.npy
              observables.npz
              states.npz   # only when ``states`` is not None
              meta.json

        Traces and states keep their shapes, including jagged traces. Archives
        contain only numeric arrays, so ``load`` can read them with
        ``allow_pickle=False``.
        """
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "times.npy", np.asarray(self.times))
        _write_archive(out / "observables.npz", [_as_float_array(obs) for obs in self.observables])
        states_path = out / "states.npz"
        if self.states is None:
            states_path.unlink(missing_ok=True)
        else:
            _write_archive(states_path, self.states)
        # Drop the previous object-array files so a re-save cannot be loaded as a pickle.
        (out / "observables.npy").unlink(missing_ok=True)
        (out / "states.npy").unlink(missing_ok=True)
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
    def load(cls, path: str | Path) -> "SimulationResult":
        """Reload a result previously written by ``save``.

        Array files are read with ``allow_pickle=False``. A numeric
        ``observables.npy`` from an older save still loads. Object-dtype arrays
        and other pickle payloads are rejected and not executed. ``states.npy``
        from an older save is refused, because that file was an object array.
        """
        root = Path(path)
        if not root.is_dir():
            raise FileNotFoundError(f"SimulationResult directory not found: {root}")
        meta_path = root / "meta.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"missing meta.json in {root}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        times = _read_npy(root / "times.npy")
        observables = _load_observables(root)
        states: list[np.ndarray] | None = None
        if meta.get("has_states", False):
            states = _load_states(root)
        return cls(
            times=times,
            observables=observables,
            states=states,
            seed=meta.get("seed"),
            algorithm=str(meta.get("algorithm", "")),
            runtime=meta.get("runtime"),
            metadata=dict(meta.get("metadata") or {}),
        )
