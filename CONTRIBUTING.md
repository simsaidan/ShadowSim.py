# Contributing

Contributions are welcome and appreciated. For larger changes, please open an
issue first to discuss scope and design.

## Development installation

Install [uv](https://docs.astral.sh/uv/), then fork and clone the repository:

```bash
git clone https://github.com/<your-github-username>/ShadowSim.py.git
cd ShadowSim.py
```

Sync the project (creates `.venv` and installs runtime plus test tools from
`uv.lock`):

```bash
uv sync
```

## Tests and coverage

```bash
uv sync
uv run pytest --cov=shadowsim --cov-config=.coveragerc --cov-report=term-missing
```

Pushes to `main` run the same in GitHub Actions and upload coverage to
[Codecov](https://app.codecov.io/gh/simsaidan/ShadowSim.py) (enable the
[Codecov GitHub app](https://github.com/apps/codecov) for this repo the first
time so uploads succeed).

## Linting

Install the lint tools, then run [Ruff](https://docs.astral.sh/ruff/) check and
format (CI runs the same checks):

```bash
uv sync --group lint
uv run --group lint ruff check .
uv run --group lint ruff format .
# CI equivalent of the format gate:
uv run --group lint ruff format --check .
```

## Adding a simulator

From a development install, scaffold a new backend with:

```bash
uv sync
uv run new-simulator --name WaveMatrix
```

Omit `--name` to be prompted. The name must be **PascalCase** (no spaces).
Names that already exist are refused. The command writes:

- `shadowsim/simulators/{name}_simulator.py` — stub with
  `# TODO: implement your simulator here`
- an export in `shadowsim/simulators/__init__.py`
- `test/simulators/test_{name}_simulator.py` — minimal tests that pass until you
  implement `simulate()`

## Pull requests

1. Fork the repository and clone your fork (see [Development installation](#development-installation)).
2. Create a feature branch:
```bash
git checkout -b feature/your-change
```
3. Make your changes and keep commits focused.
4. Run tests and Ruff locally (`uv run pytest` and the [linting](#linting) commands above).
5. Open a pull request with a clear description of what changed and why.
