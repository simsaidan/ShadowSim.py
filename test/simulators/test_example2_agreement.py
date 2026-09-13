"""Integration check: reduced Example 2 setup, QuTiP vs SplitJMatrix agreement."""

import pytest

from shadowsim.benchmarking import Benchmark
from shadowsim.models import tavis_cummings
from shadowsim.simulators import QutipSimulator, SplitJMatrixSimulator

# Reduced vs examples/simple_algo_benchmark.py (0.25, 301, num_steps=40, shots=10000).
TOTAL_TIME = 0.25
TIME_STEPS = 6
NUM_STEPS = 15
SHOTS = 1500

# QuTiP is deterministic. SplitJ disagreement is shot noise (~1/sqrt(shots) on
# empirical populations; cavity scales ~0-3) plus systematic split-J/Trotter
# bias that does not vanish with more shots. On this reduced config, local
# multi-trial max-abs errors were ~0.05; tolerances leave ~2-3x headroom so CI
# stays non-flaky while still catching order-of-magnitude regressions.
TOL_CAVITY = 0.15
TOL_EMITTER = 0.12


@pytest.mark.slow
def test_example2_qutip_splitjmatrix_agreement():
    model = tavis_cummings()

    qutip_simulator = QutipSimulator(
        model.full_hamiltonians,
        model.c_ops_full,
        model.psi0,
        model.e_ops,
        model.num_qubits,
        TOTAL_TIME,
        TIME_STEPS,
    )
    splitjmatrix_simulator = SplitJMatrixSimulator(
        model.local_hamiltonians,
        model.c_ops_local,
        model.psi0,
        model.num_qubits,
        TOTAL_TIME,
        TIME_STEPS,
        NUM_STEPS,
        measurement_groups=model.measurement_groups,
        reducers=list(model.reducers),
        shots=SHOTS,
    )

    benchmark = Benchmark(qutip_simulator, splitjmatrix_simulator)
    benchmark.run()

    metrics = benchmark.error_metrics()
    assert len(metrics) == 1
    observables = metrics[0]["observables"]
    assert len(observables) == 2

    labels_and_tols = (
        ("cavity population", TOL_CAVITY),
        ("emitter population", TOL_EMITTER),
    )
    for obs, (label, tol) in zip(observables, labels_and_tols, strict=True):
        assert obs["linf"] < tol, f"{label}: max abs error {obs['linf']:.4f} exceeds tolerance {tol}"
