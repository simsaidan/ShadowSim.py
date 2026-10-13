"""Tests for CircuitBackend execution targets."""

import numpy as np
import pytest

pytestmark = pytest.mark.qiskit

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")
pytest.importorskip("scipy")

from qiskit import QuantumCircuit

import shadowsim.simulators.circuit_backend as circuit_backend_module
from shadowsim.core import LocalHamiltonian, State
from shadowsim.simulators import SplitJMatrixSimulator, TrotterizationSimulator
from shadowsim.simulators.circuit_backend import QiskitCircuitBackend

Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_SIMULATORS = [SplitJMatrixSimulator, TrotterizationSimulator]


def _settings(**kwargs):
    defaults = {
        "hamiltonians": [LocalHamiltonian(Z, [0])],
        "lindblads": [],
        "initial_state": State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        "num_qubits": 1,
        "total_time": 0.1,
        "time_steps": 1,
        "num_steps": 1,
        "shots": 4,
        "seed": 7,
    }
    defaults.update(kwargs)
    return defaults


def _forbid_aer(*args, **kwargs):
    raise AssertionError("AerSimulator was constructed")


class _RecordingBackend:
    """Return fixed counts and record each call."""

    def __init__(self):
        self.name = "recording"
        self.calls = []

    def run_counts(self, circuit, *, shots, seed):
        self.calls.append((shots, seed))
        return {"1": 4}


class _WrappedBackend:
    """Stand in for a BackendV2 whose run method is observable."""

    def __init__(self):
        self.runs = []

    def run(self, compiled, shots):
        self.runs.append((compiled, shots))

        class _Job:
            def result(self):
                class _Result:
                    def get_counts(self):
                        return {"1": 4}

                return _Result()

        return _Job()


@pytest.mark.parametrize("cls", _SIMULATORS)
def test_default_backend_passes_seed_simulator(monkeypatch, cls):
    ctor_kwargs = []

    class FakeResult:
        def get_counts(self):
            return {"0": 1}

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeBackend:
        def __init__(self, **kwargs):
            ctor_kwargs.append(kwargs)

        def run(self, compiled, shots):
            return FakeJob()

    monkeypatch.setattr(circuit_backend_module, "AerSimulator", FakeBackend)
    monkeypatch.setattr(circuit_backend_module, "transpile", lambda circ, backend: circ)

    result = cls(**_settings()).simulate()

    assert ctor_kwargs == [{"seed_simulator": 7}]
    assert result.metadata["circuit_backend"] == "aer"


def test_one_fake_backend_drives_both_simulators(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _forbid_aer)
    backend = _RecordingBackend()

    for cls in _SIMULATORS:
        result = cls(**_settings(circuit_backend=backend)).simulate()
        assert result.metadata["circuit_backend"] == "recording"
        np.testing.assert_allclose(result.observables[0], [1.0])

    assert backend.calls == [(4, 7), (4, 7)]


def test_qiskit_circuit_backend_runs_wrapped_backend(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "AerSimulator", _forbid_aer)
    wrapped = _WrappedBackend()
    transpiled_to = []

    def fake_transpile(circ, backend):
        transpiled_to.append(backend)
        return circ

    monkeypatch.setattr(circuit_backend_module, "transpile", fake_transpile)
    backend = QiskitCircuitBackend(wrapped, name="lab")

    for cls in _SIMULATORS:
        result = cls(**_settings(circuit_backend=backend)).simulate()
        assert result.metadata["circuit_backend"] == "lab"

    assert transpiled_to == [wrapped, wrapped]
    assert len(wrapped.runs) == 2
    assert all(shots == 4 for _compiled, shots in wrapped.runs)


def test_qiskit_circuit_backend_requires_get_counts(monkeypatch):
    monkeypatch.setattr(circuit_backend_module, "transpile", lambda circ, backend: circ)

    class _Result:
        pass

    class _Job:
        def result(self):
            return _Result()

    class _Backend:
        def run(self, compiled, shots):
            return _Job()

    circuit = QuantumCircuit(1)
    circuit.measure_all()
    with pytest.raises(TypeError, match="get_counts"):
        QiskitCircuitBackend(_Backend()).run_counts(circuit, shots=1, seed=1)
