"""Time NumPy and Qulacs on one closed Trotter circuit.

Prints seconds for 14, 16, and 18 qubits. Not collected by pytest.
Requires the qiskit and qulacs extras.
"""

from time import perf_counter

from shadowsim.backends import NumpyCircuitBackend, QulacsCircuitBackend
from shadowsim.models import ising
from shadowsim.simulators import TrotterizationSimulator

_WIDTHS = (14, 16, 18)


def _circuit(num_qubits: int):
    """Return one open transverse-field Ising circuit at the final time."""
    model = ising(
        n_qubits=num_qubits,
        J=1.0,
        h=0.5,
        field="transverse",
        topology="chain",
        boundary="open",
    )
    simulator = TrotterizationSimulator(
        model.local_hamiltonians,
        [],
        model.psi0,
        num_qubits=num_qubits,
        total_time=1.0,
        time_steps=2,
        num_steps=4,
        circuit_backend=NumpyCircuitBackend(),
    )
    return simulator.metrics_circuit()


def main() -> None:
    """Print one timed ⟨Z⟩ evaluation per backend at each width."""
    numpy_backend = NumpyCircuitBackend()
    qulacs_backend = QulacsCircuitBackend()
    print(f"{'qubits':>6}  {'numpy_s':>10}  {'qulacs_s':>10}  {'max_abs_diff':>12}")
    for num_qubits in _WIDTHS:
        circuit = _circuit(num_qubits)
        qubits = list(range(num_qubits))
        numpy_backend.z_expectations(circuit, qubits, shots=1, seed=None)
        qulacs_backend.z_expectations(circuit, qubits, shots=1, seed=None)
        started = perf_counter()
        numpy_values = numpy_backend.z_expectations(circuit, qubits, shots=1, seed=None)
        numpy_seconds = perf_counter() - started
        started = perf_counter()
        qulacs_values = qulacs_backend.z_expectations(circuit, qubits, shots=1, seed=None)
        qulacs_seconds = perf_counter() - started
        difference = max(abs(left - right) for left, right in zip(numpy_values, qulacs_values, strict=True))
        print(f"{num_qubits:6d}  {numpy_seconds:10.4f}  {qulacs_seconds:10.4f}  {difference:12.3e}")


if __name__ == "__main__":
    main()
