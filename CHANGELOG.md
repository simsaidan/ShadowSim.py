# Changelog

## 1.0.0

First stable release of ShadowSim.py. The package builds and inspects shadow Hamiltonians for small qubit systems, and it benchmarks open- and closed-system simulation algorithms against a classical reference.

This release includes:

- Python packages `shadowsim.core`, `encoding`, `shadow`, `simulators`, `models`, `backends`, `benchmarking`, and `interop`. The core install depends only on NumPy.
- The version 1 run document, shared by the simulation builder and `shadowsim model`, `simulate`, `compare`, and `run`.
- `shadowsim serve` and its documented flags. The builder page lays lanes out left to right: initial state, model, method, measure, then. It offers the catalogs for those lanes, and Run, Save, Export, Import, and the results panel.
- `new-backend` and `new-simulator`, with the documented flags and the module, export, and test file each command writes.
- The documented examples: `examples/simple_shadow.py`, `examples/simple_algo_benchmark.py`, `examples/ising_chain.py`, `examples/state_encoding.py`, and `examples/coupled_oscillators.py`.
- Optional extras `qutip`, `qiskit`, `viz`, `pauli_propagation`, `qulacs`, `cirq`, `circuits`, `yaml`, and `all`.

Patch releases (`1.0.1`) and minor releases (`1.1.0`) keep this surface working for existing callers. A minor release can add a package, a command flag, an extra, or an optional argument that has a default. Spacing, color, and type on the builder page can change in a patch. Removing a lane, reordering the lanes, or dropping Run, Save, Export, Import, or the results panel is a new major version. Renaming or removing an extra is a new major version. A release that breaks the surface above is `2.0.0`. Pinning `shadowsim==1.0.0`, or citing that release's DOI, keeps this snapshot.

`pauli_propagation` stays on `juliacall==0.9.36` for the whole 1.x line. `juliacall` 0.9.37 requires CondaPkg 0.2.38, which needs JSON.jl 1.2, and the PauliPropagation revision allows only JSON 0.21. Moving off that pin, or dropping the extra, waits for 2.0.0. A newer release of QuTiP, Qiskit, or the other unpinned extras is allowed when it still meets the floors in `pyproject.toml`.

1.0.0 does not include GPU-backed shadow construction, an open-system Lindblad extension of the shadow Hamiltonian, or a reduced smoke grid for Example 2. `examples/simple_algo_benchmark.py` stays at the paper-scale time grid and shot budget.
