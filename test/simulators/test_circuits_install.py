"""The circuits extra runs a closed Trotter step without Qiskit."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.circuits

_ROOT = Path(__file__).resolve().parents[2]


def test_circuits_extra_runs_a_closed_numpy_step() -> None:
    completed = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "check_circuits_install.py"), "numpy"],
        check=False,
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
