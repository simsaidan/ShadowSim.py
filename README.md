# ShadowSim.py

## Overview

ShadowSim.py is an open-source Python library with two main purposes:

1. **Shadow Hamiltonian research**: support analysis and further research on shadow Hamiltonian simulation.
2. **Algorithm comparison**: make it easy to compare quantum simulation algorithms for **open** and **closed** systems.

## Installation

### Install from GitHub

#### 1) Fork and clone the repository
Fork this repository to your own GitHub account, then clone your fork:
```bash
git clone https://github.com/<your-github-username>/ShadowSim.py.git
cd ShadowSim.py
```

#### 2) Create and activate a virtual environment (recommended)
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3) Install dependencies
```bash
pip install --upgrade pip
pip install numpy scipy matplotlib qutip qiskit qiskit-aer
```

### Install with pip (coming soon)

`pip install ShadowSim.py` support is coming soon.

## Usage

The following simulators are supported by the package:

| Name | Type | Can handle open systems |
| --- | --- | --- |
| Qutip simulator | classical | true |
| Split JMatrix | quantum-inspired | true |
| Trotterization (coming soon) | — | — |
| Wave matrix Lindbladization (coming soon) | — | — |
| Pauli propagation (coming soon) | — | — |

## Examples

### Example 1: Exploring a simple shadow simulation example

### Example 2: Comparing a quantum algorithm against a classical solver

Imagine a scenario in which you want to compare the results of a new quantum
simulation algorithm against a source of truth like QuTiP. 
```python
```

We first define some constants used in our system:
```python
# Define system parameters
omega_c = 245000
omega_e = 245000
kappa = np.sqrt(24.5)
gamma = np.sqrt(0.4)
g = 100

a = (
    np.outer(zero_state_two_qubits, one_state_two_qubits)
    + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
    + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
)

zero = np.array([1, 0], dtype=np.complex128)
one = np.array([0, 1], dtype=np.complex128)
sigma = np.outer(zero, one)
```

Now that the system constants are built, let's define our operators. Since this
is an open-system simulation we have both Hamiltonians and Lindblad operators.

```python
H1 = omega_c * a.conjugate().T @ a
H2 = omega_e * np.outer(one, one)
H3 = g * (np.kron(a, sigma.conjugate().T) + np.kron(a.conjugate().T, sigma))

local_hamiltonians = [
    LocalHamiltonian(H1, [0, 1]),
    LocalHamiltonian(H2, [2]),
    LocalHamiltonian(H3, [0, 1, 2]),
]
full_hamiltonians = [
    Hamiltonian(tensor([H1, I])),
    Hamiltonian(tensor([I, I, H2])),
    Hamiltonian(H3),
]

# Define Lindblad operators
L1_full = Operator(kappa * np.kron(a, I))
L2_full = Operator(gamma * (tensor([I, I, sigma])))
L1_local = LocalOperator(kappa * a, [0, 1])
L2_local = LocalOperator(gamma * sigma, [2])

# Define initial state
psi_0 = State(tensor([two_state_two_qubits, zero]), 3)
```

Next, we create two simulators, one for the new algorithm and one for the 
source of truth. 

```python
# Qutip simulator
qutip_simulator = QutipSimulator(
    full_hamiltonians,
    [L1_full, L2_full],
    psi_0,
    [
        Operator(tensor([a.conjugate().T @ a, I])),
        Operator(tensor([I, I, sigma.conjugate().T @ sigma])),
    ],
    3,
    0.25,
    301,
)
# Split JMatrix simulator
splitjmatrix_simulator = SplitJMatrixSimulator(
    local_hamiltonians,
    [L1_local, L2_local],
    psi_0,
    3,
    0.25,
    301,
    40,
    measurement_groups=[[1, 2], 3],
    reducers=[_cavity_population, _population_one],
)
```

To easily compare results, we initialize a benchmark with both simulators. The 
two simulators must have the same time steps to compare apples to apples.
We run the benchmark, which runs the underlying simulations. We can visualize
the result by calling save_result_plot which saves the two simulation results 
and an absolute value comparison.

```python
benchmark = Benchmark(qutip_simulator, splitjmatrix_simulator)
benchmark.run()
paths = benchmark.save_result_plot(labels=["cavity population", "emitter population"])
for path in paths:
    print(f"Saved: {path}")
```

**Output**

*QuTiP (reference):*

![QuTiP expectations](docs/images/example2_qutip.png)

*Split JMatrix:*

![Split JMatrix expectations](docs/images/example2_split_jmatrix.png)

*Absolute difference between the two:*

![Absolute difference between the two simulators](docs/images/example2_abs_diff.png)

## Documentation

## Contributing

Contributions are welcome and appreciated.

1. Fork the repository and clone your fork (see the Installation section).
2. Create a feature branch:
```bash
git checkout -b feature/your-change
```
3. Make your changes and keep commits focused.
4. Run tests and any relevant checks locally.
5. Open a pull request with a clear description of what changed and why.

For larger changes, please open an issue first to discuss scope and design.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Citing

## References

- Somma, R. D., King, R., Kothari, R., O'Brien, T., and Babbush, R. *Shadow Hamiltonian Simulation*. [`arXiv:2407.21775`](https://arxiv.org/abs/2407.21775), [PDF](https://arxiv.org/pdf/2407.21775).
- Sims, A. N., Patel, D., Philip, A., Rubin, A. H., Bandyopadhyay, R., Radulaski, M., and Wilde, M. M. *Digital Quantum Simulations of the Non-Resonant Open Tavis-Cummings Model*. [`arXiv:2501.18522v2`](https://arxiv.org/abs/2501.18522v2), [PDF](https://arxiv.org/pdf/2501.18522v2).

