# Agent notes

Never push to `main`, even if you can bypass branch protections. Open a pull request from a branch instead.

Before opening a pull request, always run **tests and coverage**, **style**, and
**type checking** below and fix any failures.

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

## Type checking

```bash
uv sync --all-extras --group types
uv run --group types mypy
```
