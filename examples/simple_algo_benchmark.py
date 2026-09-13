from shadowsim.benchmarking import Benchmark
from shadowsim.models import tavis_cummings
from shadowsim.simulators import QutipSimulator, SplitJMatrixSimulator

model = tavis_cummings()

qutip_simulator = QutipSimulator(
    model.full_hamiltonians,
    model.c_ops_full,
    model.psi0,
    model.e_ops,
    model.num_qubits,
    0.25,
    301,
)
splitjmatrix_simulator = SplitJMatrixSimulator(
    model.local_hamiltonians,
    model.c_ops_local,
    model.psi0,
    model.num_qubits,
    0.25,
    301,
    40,
    measurement_groups=model.measurement_groups,
    reducers=list(model.reducers),
    shots=10000,
    seed=0,
)

benchmark = Benchmark(qutip_simulator, splitjmatrix_simulator)
benchmark.run()
for challenger in benchmark.error_metrics():
    print(f"Error metrics for {challenger['challenger_id']}:")
    for obs in challenger["observables"]:
        print(
            f"  observable {obs['index']}: L∞={obs['linf']:.6g}, L2={obs['l2']:.6g}, MAE={obs['mae']:.6g}, RMSE={obs['rmse']:.6g}"
        )
for resource in benchmark.resource_metrics():
    shots = resource["total_shots"]
    shots_s = "n/a" if shots is None else str(shots)
    print(f"Resources for {resource['simulator_id']}: wall_time_s={resource['wall_time_s']:.6g}, total_shots={shots_s}")
metrics_path = benchmark.save_error_metrics()
print(f"Saved: {metrics_path}")
paths = benchmark.save_result_plot(labels=["cavity population", "emitter population"])
for path in paths:
    print(f"Saved: {path}")
