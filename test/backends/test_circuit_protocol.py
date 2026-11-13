"""CircuitBackend is available without importing Qiskit."""

import importlib
import subprocess
import sys

import pytest

from shadowsim import backends
from shadowsim._optional import import_optional


def test_protocol_import_does_not_load_qiskit() -> None:
    script = """
import sys
import shadowsim.backends.circuit as circuit
from shadowsim.backends import CircuitBackend
assert CircuitBackend is circuit.CircuitBackend
assert "qiskit" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_qiskit_translation_exports_require_qiskit(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str, package: str | None = None):
        if name == "qiskit" or name.startswith("qiskit."):
            raise ModuleNotFoundError("No module named 'qiskit'", name="qiskit")
        return importlib.import_module(name, package)

    monkeypatch.delitem(backends.__dict__, "from_qiskit", raising=False)
    monkeypatch.delitem(backends.__dict__, "to_qiskit", raising=False)
    monkeypatch.setattr("shadowsim._optional.importlib.import_module", missing)

    with pytest.raises(ImportError, match=r"shadowsim\[qiskit\]"):
        import_optional("qiskit", extra="qiskit")
    with pytest.raises(ImportError, match=r"shadowsim\[qiskit\]"):
        backends.from_qiskit
    with pytest.raises(ImportError, match=r"shadowsim\[qiskit\]"):
        backends.to_qiskit
