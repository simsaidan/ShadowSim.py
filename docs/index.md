---
hide:
  - navigation
  - toc
---

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } __Docs__

    ---

    Browse the [API reference](reference/shadowsim/index.md), generated from the package.

-   :material-console:{ .lg .middle } __CLI__

    ---

    Use the [command-line interface](cli.md) for the builder UI and research commands.

-   :material-github:{ .lg .middle } __Source__

    ---

    [:octicons-arrow-right-24: Repository](https://github.com/simsaidan/ShadowSim.py)

</div>

---

!!! note "Version 1.0"
    The documented Python packages, the version 1 run document, `shadowsim serve` and the research commands, the builder lanes and actions, `new-backend` and `new-simulator`, the documented examples, and the named extras stay compatible through the 1.x line. A break to that surface is a new major version. Details are in the [changelog](https://github.com/simsaidan/ShadowSim.py/blob/main/CHANGELOG.md).

## Background

ShadowSim builds shadow Hamiltonians for small qubit systems, following shadow Hamiltonian simulation [@somma2024shadow]. The open cavity–emitter example is a Tavis–Cummings model [@sims2025tavis]. The single-emitter factory is Jaynes–Cummings.

\bibliography

## Local preview

```bash
uv sync --group docs --extra qutip --extra qiskit
uv run mkdocs serve
```

Open the URL printed in the terminal (usually `http://127.0.0.1:8000`).

The API reference is generated from `shadowsim`. Optional backends are imported during the build, so the `qutip` and `qiskit` extras need to be installed. The `qiskit` extra also installs SciPy, which the product-formula simulators import. The docs build does not install the `qulacs` or `cirq` extras: `QulacsCircuitBackend` and `CirqCircuitBackend` import those libraries only when a circuit runs. Tests that run those backends with a product-formula simulator use the `circuits` marker together with `qulacs` or `cirq` and `cross_extra`.

## Customizing this site

Edit **`mkdocs.yml`** (theme, colors, fonts, nav) and add Markdown files under **`docs/`**. The API section is filled in by `mkdocs-api-autonav`. Push to `main` to redeploy.
