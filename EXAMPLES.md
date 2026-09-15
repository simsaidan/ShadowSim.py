# Examples

Runnable scripts live in [`examples/`](examples/). After a development install
(`uv sync` from the repo root), run them with `uv run python examples/<script>.py`.

For practical scale limits (sparse vs dense, closure size, simulators), see
[Scalability / practical limits](README.md#scalability--practical-limits) in
the main README.

## Example 1: Exploring a simple shadow simulation

The complete example is in [`examples/simple_shadow.py`](examples/simple_shadow.py):

```bash
uv run python examples/simple_shadow.py
```

That example uses Pauli labels (sparse construction path) and
`run_shadow_simulation` for the reduced shadow dynamics.
Pass `verbose=True` to `run_shadow_simulation` if you want Pauli-set and
closure sizes printed.

## Example 2: Comparing a quantum algorithm against a classical solver

This is a paper-scale QuTiP vs Split JMatrix + Aer comparison (`301` time points
and a non-trivial shot budget)—expect long wall time and nontrivial Aer cost; it
is not a CI smoke test. The runnable script
[`examples/simple_algo_benchmark.py`](examples/simple_algo_benchmark.py) uses the
same scale; there is no reduced smoke grid yet.

Imagine a scenario in which you want to compare the results of a new quantum
simulation algorithm against a source of truth like QuTiP.

We build the open cavity–emitter (Tavis–Cummings–like) model with the shared
factory. Defaults match the historical Example 2 parameters; pass
`n_emitters`, `g`, `kappa`, and friends to change the physics without rewriting
operator embeddings.

```python
from shadowsim.benchmarking import Benchmark
from shadowsim.models import tavis_cummings
from shadowsim.simulators import QutipSimulator, SplitJMatrixSimulator

model = tavis_cummings()
```

Next, we create two simulators, one for the new algorithm and one for the
source of truth.

```python
# Qutip simulator
qutip_simulator = QutipSimulator(
    model.full_hamiltonians,
    model.c_ops_full,
    model.psi0,
    model.e_ops,
    model.num_qubits,
    0.25,
    301,
)
# Split JMatrix simulator
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
)
```

To easily compare results, we initialize a benchmark with a reference simulator
and one or more challengers. All simulators must share the same time grid.
We run the benchmark, which runs the underlying simulations. Numeric L∞ / L2 /
MAE / RMSE error metrics vs the reference are available via `error_metrics`.
Wall-clock time and shot budget (when a simulator exposes `shots`) are available
via `resource_metrics`. Both are exported together by `save_error_metrics` as
`{"errors": ..., "resources": ...}`. We can also visualize the result by calling
`save_result_plot`, which saves a plot per simulator and an absolute-difference
plot vs the reference for each challenger.

QuTiP is deterministic. Split JMatrix estimates populations from a finite
`shots` budget, so absolute-difference plots move run to run unless you set
`seed` (wired into Aer’s `seed_simulator`). Residual disagreement also includes
systematic split-J / Trotter bias that does not vanish with more shots. Use a
lower `shots` for smoke checks and a higher budget for publication figures; pass
`verbose=True` or a `progress(step, total)` callback for long-run feedback.

```python
benchmark = Benchmark(qutip_simulator, splitjmatrix_simulator)
benchmark.run()
print(benchmark.error_metrics())
print(benchmark.resource_metrics())
metrics_path = benchmark.save_error_metrics()
paths = benchmark.save_result_plot(labels=["cavity population", "emitter population"])
for path in [metrics_path, *paths]:
    print(f"Saved: {path}")
```

**Output**

*QuTiP (reference):*

![QuTiP expectations](./images/example2_qutip.png)

*Split JMatrix:*

![Split JMatrix expectations](./images/example2_split_jmatrix.png)

*Absolute difference between the two:*

![Absolute difference between the two simulators](./images/example2_abs_diff.png)
