"""Load a classical vector from a file for state encoding."""

import os
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt

_NUMERIC_KINDS = frozenset("iufc")
_REAL_KINDS = frozenset("iuf")


def load_encoding_data(path: str | os.PathLike[str]) -> npt.NDArray[np.number[Any]]:
    """Load a non-empty 1D vector from an encoding data file.

    ``.npy`` files are read with ``allow_pickle=False`` and may contain finite
    real or complex numbers. ``.txt`` and ``.csv`` files are one column of
    finite real numbers. Complex values belong in ``.npy``. The returned array
    is passed to an encoder such as ``AmplitudeEncoding``, ``AngleEncoding``,
    or ``ComputationalBasisEncoding``.

    Args:
        path: Path to a ``.npy``, ``.txt``, or ``.csv`` file. The suffix match
            is case-insensitive.

    Returns:
        The file's vector. A ``.npy`` array keeps its dtype. Text files are
        returned as ``float64``.

    Raises:
        ValueError: If the suffix is not supported, the path is missing, is a
            directory, or is empty, or the contents are not a non-empty 1D
            array of finite numbers. Pickle payloads are rejected and not
            executed.

    Examples:
        ```python exec="1" source="above" result="text"
        import tempfile
        from pathlib import Path

        import numpy as np

        from shadowsim.encoding import AmplitudeEncoding, load_encoding_data

        amplitudes = np.array([1.0, 1.0j, 0.0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "amplitudes.npy"
            np.save(path, amplitudes)
            state = AmplitudeEncoding().encode(load_encoding_data(path))
        print(state.get_num_qubits())
        ```

    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in {".npy", ".txt", ".csv"}:
        raise ValueError(f"encoding data path must end in .npy, .txt, or .csv, got suffix {file_path.suffix!r}")
    if not file_path.exists():
        raise ValueError(f"encoding data file does not exist: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"encoding data path must be a file: {file_path}")
    if file_path.stat().st_size == 0:
        raise ValueError(f"encoding data file is empty: {file_path}")

    if suffix == ".npy":
        return _require_vector(_read_npy(file_path), allow_complex=True)
    delimiter = "," if suffix == ".csv" else None
    return _require_vector(_read_text(file_path, delimiter), allow_complex=False)


def _read_npy(path: Path) -> np.ndarray:
    """Return the array stored in a ``.npy`` file, without unpickling."""
    try:
        loaded = np.load(path, allow_pickle=False)
        return np.asarray(loaded)
    except (OSError, EOFError, ValueError) as exc:
        raise ValueError(f"could not load encoding data from {path}") from exc


def _read_text(path: Path, delimiter: str | None) -> np.ndarray:
    """Return one column of real numbers from a text file."""
    try:
        return np.loadtxt(path, delimiter=delimiter, ndmin=1)
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not load encoding data from {path}") from exc


def _require_vector(array: np.ndarray, *, allow_complex: bool) -> npt.NDArray[np.number[Any]]:
    """Return ``array`` when it is a non-empty 1D vector of finite numbers."""
    kinds = _NUMERIC_KINDS if allow_complex else _REAL_KINDS
    if allow_complex:
        message = "encoding data must be a non-empty 1D array of finite real or complex numbers"
    else:
        message = "encoding data must be a non-empty 1D array of finite real numbers"
    if array.ndim != 1 or array.size == 0 or array.dtype.kind not in kinds:
        raise ValueError(message)
    if not np.all(np.isfinite(array)):
        raise ValueError(message)
    return cast(npt.NDArray[np.number[Any]], array)
