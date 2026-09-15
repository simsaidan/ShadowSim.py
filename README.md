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

```bash
python -m pip install git+https://github.com/simsaidan/ShadowSim.py.git
```

The package can then be imported as `shadowsim`.

For a local development install (`uv sync`, tests, lint, scaffolding a simulator),
see [CONTRIBUTING.md](CONTRIBUTING.md).

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

See [EXAMPLES.md](EXAMPLES.md) for walkthroughs. Runnable scripts:

- [`examples/simple_shadow.py`](examples/simple_shadow.py) — sparse shadow construction and reduced dynamics
- [`examples/simple_algo_benchmark.py`](examples/simple_algo_benchmark.py) — QuTiP vs Split JMatrix + Aer (paper-scale; long-running)

## Documentation

- [API / site docs](https://simsaidan.github.io/ShadowSim.py/) (`docs/`; preview with `uv sync --group docs && uv run mkdocs serve`)
- [Examples](EXAMPLES.md)
- [Contributing](CONTRIBUTING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, tests, linting,
simulator scaffolding, and pull-request guidelines.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Citing

DOI coming soon.

## References

- [![arXiv](https://img.shields.io/static/v1?label=arXiv&message=2407.21775&color=inactive&style=flat-square)](https://arxiv.org/abs/2407.21775) Somma, R. D., King, R., Kothari, R., O'Brien, T., and Babbush, R. *Shadow Hamiltonian Simulation*. [PDF](https://arxiv.org/pdf/2407.21775)
- [![arXiv](https://img.shields.io/static/v1?label=arXiv&message=2501.18522&color=inactive&style=flat-square)](https://arxiv.org/abs/2501.18522v2) Sims, A. N., Patel, D., Philip, A., Rubin, A. H., Bandyopadhyay, R., Radulaski, M., and Wilde, M. M. *Digital Quantum Simulations of the Non-Resonant Open Tavis-Cummings Model*. [PDF](https://arxiv.org/pdf/2501.18522v2)
