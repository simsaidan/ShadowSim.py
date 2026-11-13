# Examples

Walkthroughs live in the root [README.md](../README.md#examples).

Runnable scripts in this directory (after `uv sync --all-extras` from the repo root):

```bash
uv run python examples/simple_shadow.py
uv run python examples/simple_algo_benchmark.py
uv run python examples/ising_chain.py
uv run python examples/state_encoding.py
uv run python examples/qulacs_benchmark.py
```

`qulacs_benchmark.py` needs the `circuits` and `qulacs` extras. `NumpyCircuitBackend` is part of the core package. `uv sync --all-extras` installs both extras. It is a timing script, not a test.
