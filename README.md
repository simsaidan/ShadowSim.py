# ShadowSim.py

[![Test and coverage](https://github.com/simsaidan/ShadowSim.py/actions/workflows/test-coverage.yml/badge.svg)](https://github.com/simsaidan/ShadowSim.py/actions/workflows/test-coverage.yml)
[![codecov](https://codecov.io/gh/simsaidan/ShadowSim.py/branch/main/graph/badge.svg)](https://app.codecov.io/gh/simsaidan/ShadowSim.py)

## Overview

ShadowSim.py is an open-source Python library with two main purposes:

1. **Shadow Hamiltonian research**: support analysis and further research on shadow Hamiltonian simulation.
2. **Algorithm comparison**: make it easy to compare quantum simulation algorithms for **open** and **closed** systems.

**Note:** “Shadow” here means *shadow Hamiltonian simulation* ([Somma et al., arXiv:2407.21775](https://arxiv.org/abs/2407.21775)), **not** classical shadow tomography / randomized measurement protocols.

**When to use:** Use ShadowSim to build and inspect shadow Hamiltonians for small qubit systems, and to benchmark open- or closed-system simulation algorithms against a classical reference (e.g. QuTiP).

## Installation

### Development installation

Install [uv](https://docs.astral.sh/uv/), then fork and clone the repository:
```bash
git clone https://github.com/<your-github-username>/ShadowSim.py.git
cd ShadowSim.py
```

Sync the project (creates `.venv` and installs runtime plus test tools from `uv.lock`):
```bash
uv sync
```

### Install directly from GitHub

```bash
python -m pip install git+https://github.com/simsaidan/ShadowSim.py.git
```

The package can then be imported as `shadowsim`.

## Tests and coverage

```bash
uv sync
uv run pytest --cov=shadowsim --cov-config=.coveragerc --cov-report=term-missing
```

Pushes to `main` run the same in GitHub Actions and upload coverage to [Codecov](https://app.codecov.io/gh/simsaidan/ShadowSim.py) (enable the [Codecov GitHub app](https://github.com/apps/codecov) for this repo the first time so uploads succeed).

## Linting

Install the lint tools, then run [Ruff](https://docs.astral.sh/ruff/) check and format (CI runs the same checks):

```bash
uv sync --group lint
uv run --group lint ruff check .
uv run --group lint ruff format .
# CI equivalent of the format gate:
uv run --group lint ruff format --check .
```

## Usage

Public objects are imported from their domain subpackages:
```python
from shadowsim.core import Hamiltonian, Operator, State
from shadowsim.shadow import ShadowHamiltonian
from shadowsim.simulators import QutipSimulator
```

The following simulators are supported by the package:

| Name | Type | Can handle open systems |
| --- | --- | --- |
| Qutip simulator | classical | true |
| Split JMatrix | quantum-inspired | true |
| Trotterization | quantum-inspired | false |
| Wave matrix Lindbladization (coming soon) | — | — |
| Pauli propagation (coming soon) | — | — |

### Adding a simulator

From a development install, scaffold a new backend with:

```bash
uv sync
uv run new-simulator --name WaveMatrix
```

Omit `--name` to be prompted. The name must be **PascalCase** (no spaces). Names that
already exist are refused. The command writes:

- `shadowsim/simulators/{name}_simulator.py` — stub with `# TODO: implement your simulator here`
- an export in `shadowsim/simulators/__init__.py`
- `test/simulators/test_{name}_simulator.py` — minimal tests that pass until you implement `simulate()`

### Sparse / Pauli-label shadow construction

Pass Pauli labels (or `PauliSum`s) for both the Hamiltonian and the observables so
`ShadowHamiltonian` can build `H_S` in label space—no `4^n` tomography and no
full `2^n × 2^n` matrix multiplies during construction:

```python
from shadowsim.core import Hamiltonian, OperatorSet
from shadowsim.shadow import ShadowHamiltonian

shadow = ShadowHamiltonian(
    OperatorSet(["XII", "YII", "ZII", "IIX"]),
    [Hamiltonian("XII"), Hamiltonian("IIX")],
)
assert shadow.used_sparse_pauli_path
print(shadow.H_S.shape)  # (|closure|, |closure|)
```

Dense matrices and `LocalHamiltonian` terms still work; they take the densifying
fallback (`used_sparse_pauli_path` is `False`). See also
[`examples/simple_shadow.py`](examples/simple_shadow.py).

For practical scale limits (sparse vs dense, closure size, simulators), see
[Scalability / practical limits](#scalability--practical-limits).

## Scalability / practical limits

### Shadow construction

- Prefer Pauli labels / `PauliSum` so `ShadowHamiltonian` takes the sparse path
  (`used_sparse_pauli_path`). Cost then tracks Hamiltonian Pauli terms × closure
  size `m`, not `4^n`.
- Dense fallback (dense matrices / `LocalHamiltonian`): practical for small `n`
  (roughly ≤3–4 as historically exercised). Bottleneck is `4^n` Pauli tomography
  plus dense `2^n` linear algebra.
- Closure size `m` can grow independently of Hilbert-space dimension; `H_S` is
  always `m×m` (not `2^n×2^n`).
- Inspect cost before a long run: `ShadowHamiltonian(..., verbose=True)` prints
  Hamiltonian Pauli count, operator-set union size, and closure size.

### What works today

| Path | Practical scale today | Bottleneck |
| --- | --- | --- |
| `ShadowHamiltonian` (Pauli labels) | few-term models; `n` past ~3–4 when closure stays small | Pauli terms × closure size `m` |
| `ShadowHamiltonian` (dense / local) | small `n` (~≤3–4) | `4^n` tomography + dense mats |
| QuTiP simulator | small truncated models | stiff ODEs / Hilbert dim |
| Split JMatrix + Aer | tiny time grids / shot budgets for smoke; set `seed` for reproducible Aer shots | circuit per timestep × shots |
| Trotterization + Aer | closed systems only; tiny time grids / shot budgets; set `seed` for reproducible Aer shots | circuit per timestep × shots |

### Not yet / still heavy

GPU-backed shadows, open-system Lindblad shadow extensions, and a reduced smoke
grid for Example 2 are not provided yet. For shadow construction, use the
[sparse / Pauli-label path](#sparse--pauli-label-shadow-construction) whenever
you already have a Pauli decomposition.

## Examples

### Example 1: Exploring a simple shadow simulation example

The complete example is in [`examples/simple_shadow.py`](examples/simple_shadow.py)
and can be run after `uv sync`:
```bash
uv run python examples/simple_shadow.py
```
That example uses Pauli labels (sparse construction path) and
`run_shadow_simulation` for the reduced shadow dynamics.
Pass `verbose=True` to `run_shadow_simulation` if you want Pauli-set and
closure sizes printed.

### Example 2: Comparing a quantum algorithm against a classical solver

This is a paper-scale QuTiP vs Split JMatrix + Aer comparison (`301` time points
and a non-trivial shot budget)—expect long wall time and nontrivial Aer cost; it
is not a CI smoke test. The runnable script
[`examples/simple_algo_benchmark.py`](examples/simple_algo_benchmark.py) uses the
same scale; there is no reduced smoke grid yet. See
[Scalability / practical limits](#scalability--practical-limits).

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

## Documentation

## Contributing

Contributions are welcome and appreciated.

1. Fork the repository and clone your fork (see the Installation section).
2. Create a feature branch:
```bash
git checkout -b feature/your-change
```
3. Make your changes and keep commits focused.
4. Run tests and Ruff locally (`uv run pytest` and the linting commands above).
5. Open a pull request with a clear description of what changed and why.

For larger changes, please open an issue first to discuss scope and design.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Citing

DOI coming soon.

## References

- [![arXiv](https://img.shields.io/static/v1?label=arXiv&message=2407.21775&color=inactive&style=flat-square)](https://arxiv.org/abs/2407.21775) Somma, R. D., King, R., Kothari, R., O'Brien, T., and Babbush, R. *Shadow Hamiltonian Simulation*. [PDF](https://arxiv.org/pdf/2407.21775)
- [![arXiv](https://img.shields.io/static/v1?label=arXiv&message=2501.18522&color=inactive&style=flat-square)](https://arxiv.org/abs/2501.18522v2) Sims, A. N., Patel, D., Philip, A., Rubin, A. H., Bandyopadhyay, R., Radulaski, M., and Wilde, M. M. *Digital Quantum Simulations of the Non-Resonant Open Tavis-Cummings Model*. [PDF](https://arxiv.org/pdf/2501.18522v2)

