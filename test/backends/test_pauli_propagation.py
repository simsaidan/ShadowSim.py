"""Tests for the PauliPropagation backend."""

import importlib.util
import math
import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")

from qiskit import QuantumCircuit

from shadowsim import backends
from shadowsim.backends.pauli_propagation import PauliPropagationBackend


def test_pauli_propagation_backend_is_exported():
    assert backends.PauliPropagationBackend is PauliPropagationBackend
    assert PauliPropagationBackend().name == "pauli_propagation"
    assert "PauliPropagationBackend" in dir(backends)


def test_run_counts_is_not_supported():
    circuit = QuantumCircuit(1)

    with pytest.raises(NotImplementedError, match="shot counts"):
        PauliPropagationBackend().run_counts(circuit, shots=1, seed=None)


def test_expectations_require_the_pauli_propagation_extra(monkeypatch):
    def missing(module: str, *, extra: str) -> object:
        raise ImportError(f"{module} requires the {extra} extra")

    monkeypatch.setattr("shadowsim.backends.pauli_propagation.import_optional", missing)
    circuit = QuantumCircuit(1)
    backend = PauliPropagationBackend()

    with pytest.raises(ImportError, match="pauli_propagation"):
        backend.z_expectations(circuit, [0], shots=1, seed=None)
    with pytest.raises(ImportError, match="pauli_propagation"):
        backend.x_expectations(circuit, [0], shots=1, seed=None)


def test_expectations_reject_an_index_outside_the_circuit():
    circuit = QuantumCircuit(1)
    backend = PauliPropagationBackend()

    with pytest.raises(ValueError, match="outside a circuit of 1 qubits"):
        backend.z_expectations(circuit, [1], shots=1, seed=None)
    with pytest.raises(ValueError, match="outside a circuit of 1 qubits"):
        backend.x_expectations(circuit, [True], shots=1, seed=None)


def test_missing_julia_package_is_reported_to_the_page(monkeypatch):
    class JuliaError(Exception):
        pass

    JuliaError.__module__ = "juliacall"

    class JuliaModule:
        def seval(self, expr):
            raise JuliaError("ArgumentError: Package PauliPropagation not found in current path.")

    class JuliaCall:
        def newmodule(self, name):
            return JuliaModule()

    monkeypatch.setattr("shadowsim.backends.pauli_propagation._julia_modules", [])
    monkeypatch.setattr(
        "shadowsim.backends.pauli_propagation.import_optional",
        lambda module, *, extra: JuliaCall(),
    )
    circuit = QuantumCircuit(1)
    circuit.h(0)

    with pytest.raises(ValueError, match="Pkg.add") as caught:
        PauliPropagationBackend().z_expectations(circuit, [0], shots=1, seed=None)
    assert "not installed" in str(caught.value)


def test_measure_and_reset_are_rejected_before_julia():
    backend = PauliPropagationBackend()
    measured = QuantumCircuit(1, 1)
    measured.measure(0, 0)
    reset = QuantumCircuit(1)
    reset.reset(0)

    with pytest.raises(ValueError, match="measure"):
        backend.z_expectations(measured, [0], shots=1, seed=None)
    with pytest.raises(ValueError, match="reset"):
        backend.z_expectations(reset, [0], shots=1, seed=None)


def test_importable_trotter_circuit_matches_the_unitary_state():
    import numpy as np
    from qiskit import qasm2
    from qiskit.quantum_info import Statevector

    from shadowsim.backends.pauli_propagation import _importable_circuit
    from shadowsim.core import LocalHamiltonian
    from shadowsim.encoding import AngleEncoding
    from shadowsim.simulators.trotterization_simulator import _trotter_circuit

    x_matrix = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
    z_matrix = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
    circuit = _trotter_circuit(
        [LocalHamiltonian(np.kron(z_matrix, z_matrix), [0, 1]), LocalHamiltonian(0.5 * x_matrix, [1])],
        AngleEncoding().encode([0.4, 0.2]),
        2,
        0.3,
        2,
        x_qubits=[0],
    )
    imported = _importable_circuit(circuit)
    overlap = np.vdot(Statevector.from_instruction(circuit).data, Statevector.from_instruction(imported).data)
    assert abs(overlap) == pytest.approx(1.0)
    exported = qasm2.dumps(imported)
    assert "reset" not in exported
    assert "measure" not in exported

    entangled = QuantumCircuit(2)
    entangled.initialize([1.0, 0.0, 0.0, 1.0] / np.sqrt(2.0), [0, 1])
    with pytest.raises(ValueError, match="product"):
        _importable_circuit(entangled)


def test_a_python_failure_inside_julia_is_reraised(monkeypatch):
    class JuliaModule:
        def seval(self, expr):
            raise RuntimeError("python blew up")

    class JuliaCall:
        def newmodule(self, name):
            return JuliaModule()

    monkeypatch.setattr("shadowsim.backends.pauli_propagation._julia_modules", [])
    monkeypatch.setattr(
        "shadowsim.backends.pauli_propagation.import_optional",
        lambda module, *, extra: JuliaCall(),
    )
    circuit = QuantumCircuit(1)
    circuit.x(0)

    with pytest.raises(RuntimeError, match="python blew up"):
        PauliPropagationBackend().z_expectations(circuit, [0], shots=1, seed=None)


def test_missing_openqasm_interface_names_the_revision(monkeypatch):
    class JuliaModule:
        def seval(self, expr):
            return False

    class JuliaCall:
        def newmodule(self, name):
            return JuliaModule()

    monkeypatch.setattr("shadowsim.backends.pauli_propagation._julia_modules", [])
    monkeypatch.setattr(
        "shadowsim.backends.pauli_propagation.import_optional",
        lambda module, *, extra: JuliaCall(),
    )
    circuit = QuantumCircuit(1)
    circuit.h(0)

    with pytest.raises(ValueError, match="OpenQASMInterface") as caught:
        PauliPropagationBackend().z_expectations(circuit, [0], shots=1, seed=None)
    assert "Pkg.add" in str(caught.value)


def test_a_julia_read_error_is_reported(monkeypatch):
    class JuliaError(Exception):
        pass

    JuliaError.__module__ = "juliacall"

    class Interface:
        def readqasm(self, path):
            raise JuliaError("ParseError: unknown gate")

    class Module:
        class PauliPropagation:
            OpenQASMInterface = Interface()

    monkeypatch.setattr("shadowsim.backends.pauli_propagation._julia_module", Module)
    circuit = QuantumCircuit(1)
    circuit.h(0)

    with pytest.raises(ValueError, match="unknown gate"):
        PauliPropagationBackend().x_expectations(circuit, [0], shots=1, seed=None)


def test_an_unreadable_gate_is_rejected(monkeypatch):
    from qiskit.circuit import Gate

    def leave_unknown(circuit, *, basis_gates, optimization_level):
        mystery = QuantumCircuit(circuit.num_qubits)
        mystery.append(Gate("mystery", 1, []), [0])
        return mystery

    monkeypatch.setattr("shadowsim.backends.pauli_propagation.transpile", leave_unknown)
    circuit = QuantumCircuit(1)
    circuit.h(0)

    with pytest.raises(ValueError, match="mystery"):
        PauliPropagationBackend().z_expectations(circuit, [0], shots=1, seed=None)


def test_product_initialize_skips_an_identity_and_prepares_one():
    import numpy as np

    from shadowsim.backends.pauli_propagation import _importable_circuit, _product_kets

    zero = QuantumCircuit(1)
    zero.initialize([1, 0], [0])
    assert _importable_circuit(zero).data == []

    one = QuantumCircuit(1)
    one.initialize([0, 1], [0])
    assert [item.operation.name for item in _importable_circuit(one).data] == ["u"]
    assert _product_kets(np.array([1.0, 2.0, 3.0])) is None
    assert _product_kets(np.zeros(2)) is None
    assert _product_kets(np.array([])) is None


def test_a_reconstruction_that_misses_the_state_is_rejected(monkeypatch):
    import numpy as np

    from shadowsim.backends.pauli_propagation import _product_kets

    monkeypatch.setattr("shadowsim.backends.pauli_propagation.np.vdot", lambda left, right: 0.0)

    assert _product_kets(np.array([1.0, 0.0])) is None


def test_propagation_reports_weight_and_julia_failures():
    from shadowsim.backends.pauli_propagation import _one_expectation

    class JuliaError(Exception):
        pass

    JuliaError.__module__ = "juliacall"

    class Propagation:
        def __init__(self):
            self.options = None

        def PauliString(self, nqubits, symbol, qubit):
            return (nqubits, symbol, qubit)

        def propagate(self, gates, observable, thetas, **options):
            self.options = options
            if options.get("max_weight") == 1:
                raise JuliaError("\n\nweight exceeded\n")
            return 1

        def overlapwithzero(self, propagated):
            return 0.25

    class Module:
        def __init__(self):
            self.PauliPropagation = Propagation()

        def seval(self, expr):
            return lambda name: name

    module = Module()
    value = _one_expectation(module, 1, [], [], "Z", 1, max_weight=2.0, min_abs_coeff=1e-8)

    assert value == 0.25
    assert module.PauliPropagation.options == {"min_abs_coeff": 1e-8, "max_weight": 2.0}
    with pytest.raises(ValueError, match="weight exceeded"):
        _one_expectation(module, 1, [], [], "Z", 1, max_weight=1.0, min_abs_coeff=1e-8)

    class BlankPropagation:
        def PauliString(self, nqubits, symbol, qubit):
            return (nqubits, symbol, qubit)

        def propagate(self, gates, observable, thetas, **options):
            raise JuliaError(" \n ")

        def overlapwithzero(self, propagated):
            return 0.0

    class BlankModule:
        PauliPropagation = BlankPropagation()

        def seval(self, expr):
            return lambda name: name

    with pytest.raises(ValueError, match="PauliPropagation failed"):
        _one_expectation(BlankModule(), 1, [], [], "Z", 1, max_weight=None, min_abs_coeff=1e-8)


def test_expectations_of_no_qubits_are_empty(monkeypatch):
    def forbidden(module: str, *, extra: str) -> object:
        raise AssertionError(f"imported {module} from the {extra} extra")

    monkeypatch.setattr("shadowsim.backends.pauli_propagation.import_optional", forbidden)
    circuit = QuantumCircuit(2)
    backend = PauliPropagationBackend()

    assert backend.z_expectations(circuit, [], shots=1, seed=None) == []
    assert backend.x_expectations(circuit, [], shots=1, seed=None) == []


def _julia_executable() -> str | None:
    """Return a Julia executable that is already installed."""
    for key in ("PYTHON_JULIACALL_EXE", "PYTHON_JULIAPKG_EXE"):
        path = os.environ.get(key)
        if path and os.path.isfile(path):
            return path
    return shutil.which("julia")


def _julia_project_dir() -> Path | None:
    """Return the Julia project juliacall will use, when that location is known."""
    for key in ("PYTHON_JULIACALL_PROJECT", "PYTHON_JULIAPKG_PROJECT"):
        path = os.environ.get(key)
        if path:
            return Path(path)
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        return Path(venv) / "julia_env"
    return None


def _project_lists_pauli_propagation(project: Path) -> bool:
    """Return whether ``project`` already installs PauliPropagation."""
    return any(
        (project / name).is_file() and "PauliPropagation" in (project / name).read_text(encoding="utf-8")
        for name in ("Project.toml", "Manifest.toml")
    )


def _pauli_propagation_skip_reason() -> str | None:
    """Return why the Julia tests cannot run, or None when the reader is available."""
    if importlib.util.find_spec("juliacall") is None:
        return "juliacall is not installed"
    if _julia_executable() is None:
        return "Julia is not installed"
    project = _julia_project_dir()
    if project is not None and not _project_lists_pauli_propagation(project):
        return "PauliPropagation is not installed"
    try:
        import juliacall

        module = juliacall.newmodule("ShadowSimPauliPropagationProbe")
        module.seval("import PauliPropagation")
        if not module.seval("isdefined(PauliPropagation, :OpenQASMInterface)"):
            return "PauliPropagation.OpenQASMInterface is unavailable"
    except Exception as exc:
        detail = str(exc).splitlines()[0] if str(exc).strip() else type(exc).__name__
        return f"PauliPropagation is unavailable ({detail})"
    return None


@pytest.fixture(scope="module")
def pauli_backend():
    reason = _pauli_propagation_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    return PauliPropagationBackend()


@pytest.mark.pauli_propagation
def test_rx_expectations(pauli_backend):
    # RX(θ)|0⟩ stays in the YZ plane, so ⟨X⟩ is 0 and ⟨Z⟩ is cos(θ).
    circuit = QuantumCircuit(1)
    circuit.rx(0.4, 0)

    assert pauli_backend.z_expectations(circuit, [0], shots=1, seed=None) == pytest.approx([math.cos(0.4)])
    assert pauli_backend.x_expectations(circuit, [0], shots=1, seed=None) == pytest.approx([0.0])


@pytest.mark.pauli_propagation
def test_expectations_follow_qubit_order(pauli_backend):
    circuit = QuantumCircuit(2)
    circuit.ry(0.4, 0)
    circuit.ry(0.2, 1)

    assert pauli_backend.z_expectations(circuit, [1, 0], shots=1, seed=None) == pytest.approx(
        [math.cos(0.2), math.cos(0.4)]
    )
    assert pauli_backend.x_expectations(circuit, [1, 0], shots=1, seed=None) == pytest.approx(
        [math.sin(0.2), math.sin(0.4)]
    )


@pytest.mark.pauli_propagation
def test_measure_is_rejected(pauli_backend):
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)

    with pytest.raises(Exception, match="measure"):
        pauli_backend.z_expectations(circuit, [0], shots=1, seed=None)
