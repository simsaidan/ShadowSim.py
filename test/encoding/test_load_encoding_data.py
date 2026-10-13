"""Loading encoding data from a file."""

import pickle
from pathlib import Path

import numpy as np
import pytest

from shadowsim.encoding import (
    AmplitudeEncoding,
    AngleEncoding,
    ComputationalBasisEncoding,
    load_encoding_data,
)

_pickle_status = {"executed": False}


def _mark_pickle_executed() -> int:
    _pickle_status["executed"] = True
    return 0


class _ExecutablePickle:
    """Pickle payload that records execution when it is unpickled."""

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (_mark_pickle_executed, ())


def _write_pickle(path: Path) -> None:
    with path.open("wb") as handle:
        pickle.dump(_ExecutablePickle(), handle)


def test_npy_complex_amplitudes_round_trip(tmp_path: Path):
    amplitudes = np.array([0.3, 0.4j, -0.1], dtype=np.complex128)
    path = tmp_path / "amplitudes.npy"
    np.save(path, amplitudes)

    loaded = AmplitudeEncoding().encode(load_encoding_data(path))
    direct = AmplitudeEncoding().encode(amplitudes)
    assert np.allclose(loaded.to_numpy(), direct.to_numpy())


def test_txt_angles_round_trip(tmp_path: Path):
    angles = np.array([0.3, -1.1, np.pi / 2])
    path = tmp_path / "angles.txt"
    np.savetxt(path, angles)

    loaded = AngleEncoding().encode(load_encoding_data(path))
    direct = AngleEncoding().encode(angles)
    assert np.allclose(loaded.to_numpy(), direct.to_numpy())


def test_txt_bit_row_round_trip(tmp_path: Path):
    path = tmp_path / "bits.txt"
    path.write_text("1 0\n")

    loaded = ComputationalBasisEncoding(2).encode(load_encoding_data(path))
    direct = ComputationalBasisEncoding(2).encode([1, 0])
    assert np.array_equal(loaded.to_numpy(), direct.to_numpy())


def test_csv_bit_row_round_trip(tmp_path: Path):
    path = tmp_path / "bits.csv"
    path.write_text("1,0\n")

    loaded = ComputationalBasisEncoding(2).encode(load_encoding_data(path))
    direct = ComputationalBasisEncoding(2).encode([1, 0])
    assert np.array_equal(loaded.to_numpy(), direct.to_numpy())


def test_rejects_two_dimensional_npy(tmp_path: Path):
    path = tmp_path / "matrix.npy"
    np.save(path, np.ones((2, 2)))
    with pytest.raises(ValueError, match="1D"):
        load_encoding_data(path)


def test_rejects_pickle_npy_without_executing(tmp_path: Path):
    path = tmp_path / "payload.npy"
    _write_pickle(path)
    raw = path.read_bytes()

    _pickle_status["executed"] = False
    pickle.loads(raw)
    assert _pickle_status["executed"]

    _pickle_status["executed"] = False
    with pytest.raises(ValueError, match="could not load"):
        load_encoding_data(path)
    assert not _pickle_status["executed"]


def test_rejects_pickle_suffix_without_reading(tmp_path: Path):
    path = tmp_path / "payload.pkl"
    _write_pickle(path)
    # Opening this file would fail. A suffix error means it was not opened.
    path.chmod(0)
    _pickle_status["executed"] = False
    try:
        with pytest.raises(ValueError, match="must end in"):
            load_encoding_data(path)
    finally:
        path.chmod(0o644)
    assert not _pickle_status["executed"]


def test_rejects_missing_path(tmp_path: Path):
    with pytest.raises(ValueError, match="does not exist"):
        load_encoding_data(tmp_path / "missing.npy")


def test_rejects_unknown_suffix(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text("[1, 0]\n")
    with pytest.raises(ValueError, match="must end in"):
        load_encoding_data(path)


def test_rejects_directory(tmp_path: Path):
    path = tmp_path / "data.npy"
    path.mkdir()
    with pytest.raises(ValueError, match="must be a file"):
        load_encoding_data(path)


def test_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        load_encoding_data(path)


def test_rejects_non_finite_value(tmp_path: Path):
    path = tmp_path / "amplitudes.npy"
    np.save(path, np.array([1.0, np.nan]))
    with pytest.raises(ValueError, match="finite"):
        load_encoding_data(path)


def test_rejects_multi_column_txt(tmp_path: Path):
    path = tmp_path / "table.txt"
    path.write_text("0.1 0.2\n0.3 0.4\n")
    with pytest.raises(ValueError, match="finite real"):
        load_encoding_data(path)
