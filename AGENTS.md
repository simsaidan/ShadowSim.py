# Agent notes

Never push to `main`, even if you can bypass branch protections. Open a pull request from a branch instead.

If the push is for an issue, the commit message should say `Resolves #<issue number>`.

Before opening a pull request, always run **tests and coverage**, **style**,
**type checking**, and **documentation** below and fix any failures.

## Tests and coverage

```bash
uv run pytest --cov=shadowsim --cov-config=.coveragerc --cov-report=term-missing
```
Coverage should always be at 100 percent unless impossible to achieve.

## Style

```bash
uv sync --group lint
uv run --group lint ruff check .
uv run --group lint ruff format --check .
```

The builder page scripts need Node 22.22.2 or newer on the 22 line, 24.15.0 or newer on the 24 line, or 26 or newer.

```bash
npm ci
npm run lint
npm test
```

`npm run coverage` reports JavaScript coverage and does not fail the build.

## Type checking

```bash
uv sync --all-extras --group types
uv run --group types mypy
```

## Documentation

The API reference is generated from the package. Optional backends are imported during the build, so the `qutip` and `qiskit` extras need to be installed.

```bash
uv sync --group docs --extra qutip --extra qiskit
uv run mkdocs build --strict
```

Preview locally with `uv run mkdocs serve`.
