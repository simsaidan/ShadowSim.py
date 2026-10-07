# Agent notes

Never push to `main`, even if you can bypass branch protections. Open a pull request from a branch instead.

Before opening a pull request, always run both **tests and coverage** and **style**
below and fix any failures.

## Tests and coverage

```bash
uv run pytest --cov=shadowsim --cov-config=.coveragerc --cov-report=term-missing
```

## Style

```bash
uv sync --group lint
uv run --group lint ruff check .
uv run --group lint ruff format --check .
```
