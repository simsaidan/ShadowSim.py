---
hide:
  - navigation
  - toc
---

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } __Docs__

    ---

    Browse the [API reference](reference/shadowsim/index.md), generated from the package.

-   :material-github:{ .lg .middle } __Source__

    ---

    [:octicons-arrow-right-24: Repository](https://github.com/simsaidan/ShadowSim.py)

</div>

---

!!! note "Work in progress"
    Public APIs are still **draft** until a stable release. Expect changes.

## Background

ShadowSim builds shadow Hamiltonians for small qubit systems, following shadow Hamiltonian simulation [@somma2024shadow]. The open cavity–emitter example is a Tavis–Cummings model [@sims2025tavis]. The single-emitter factory is Jaynes–Cummings.

\bibliography

## Local preview

```bash
uv sync --group docs --extra qutip --extra qiskit
uv run mkdocs serve
```

Open the URL printed in the terminal (usually `http://127.0.0.1:8000`).

The API reference is generated from `shadowsim`. Optional backends are imported during the build, so the `qutip` and `qiskit` extras need to be installed. The docs build does not install the `qulacs` or `cirq` extras: `QulacsCircuitBackend` and `CirqCircuitBackend` import those libraries only when a circuit runs. Tests that need them use the `qulacs` or `cirq` marker, together with `cross_extra`, because they also need Qiskit.

## Customizing this site

Edit **`mkdocs.yml`** (theme, colors, fonts, nav) and add Markdown files under **`docs/`**. The API section is filled in by `mkdocs-api-autonav`. Push to `main` to redeploy.
