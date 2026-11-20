# Command-line interface

The `shadowsim` entry point covers two workflows:

- **Builder UI** — `shadowsim serve` opens the local simulation builder page.
- **Research commands** — `model`, `simulate`, `compare`, and `run` construct and execute the same version 1 run documents the builder posts, without writing Python.

Install the package so the console script is on your `PATH` (a normal pip/`uv` install is enough). Product-formula runs need the `circuits` extra; Aer comparison needs `qiskit`; YAML experiment files need `yaml`:

```bash
python -m pip install "shadowsim[circuits,qiskit,yaml]"
shadowsim --help
```

## Builder: `serve`

```bash
shadowsim serve
shadowsim serve --host 127.0.0.1 --port 8000 --output-dir results --no-browser
```

`serve` binds a local HTTP(S) server, serves the builder page, and accepts the same run documents over `POST /runs`. Non-loopback binds require `--allow-remote` and TLS. See `shadowsim serve --help` for the full flag list.

## Research commands

All research verbs compile into (or load) a **version 1 run document** and call the same build/run path as the builder (`check_page` / `run_page`). Catalog ids for models, simulators, backends, states, and measurements match the builder cards.

### `model`

Validate factory arguments and print a model stub:

```bash
shadowsim model ising --qubits 8 --J 1.0 --h 0.5 --topology chain --boundary open
shadowsim model ising --qubits 4 --format json
```

### `simulate`

Run one simulator (optional circuit backend):

```bash
shadowsim simulate \
  --model ising --qubits 8 --J 1.0 \
  --simulator trotterization --time-steps 11 --num-steps 10 \
  --backend aer --shots 1000 --seed 42 \
  --state basis --state-value 00000000 \
  --measure model \
  --save results/ising --format text
```

Useful shared flags:

| Flag | Role |
| --- | --- |
| `--total` | Evolution time (default `0.5`) |
| `--state` / `--state-value` | Initial state id and payload |
| `--measure` / `--sites` / `--expression` | Measurement selection |
| `--save` / `--export` | Write results / metrics JSON |
| `--output-dir` | Root that save/export paths must stay under |
| `--format text\|json` | Stdout summary or full payload |
| `--print-document` | Print the v1 document as JSON and exit |

Simulator and backend chip fields from the catalogs are exposed as flags (`--time-steps`, `--num-steps`, `--shots`, …).

### `compare`

Run one simulator on **at least two** backends. The first backend is the benchmark reference:

```bash
shadowsim compare \
  --model ising --qubits 4 \
  --simulator trotterization --time-steps 5 --num-steps 4 \
  --backends numpy,aer,qulacs \
  --export results/compare.json --format json
```

Comparing different simulator classes (not just backends) is done with a multi-entry run document via `shadowsim run`, the same shape the builder uses when several simulator cards are selected.

### `run`

Execute a document from disk:

```bash
shadowsim run experiment.json
shadowsim run experiment.yaml   # needs shadowsim[yaml]
shadowsim run experiment.json --print-document
```

## Run document schema

Machine configuration is the builder's version 1 JSON object. Required top-level keys are:

`version`, `total`, `state`, `model`, `simulators`, `measure`, `actions`

A minimal closed-system example:

```json
{
  "version": 1,
  "total": "0.5",
  "state": {"id": "basis", "value": "00"},
  "model": {"id": "ising", "arguments": {"n_qubits": 2}},
  "simulators": [
    {
      "id": "trotterization",
      "arguments": {"time_steps": 2, "num_steps": 1},
      "backend": {"id": "numpy", "arguments": {}}
    }
  ],
  "measure": {"id": "model", "sites": null},
  "actions": {"ids": []}
}
```

YAML files use the same object shape. Validation, caps, and error messages are shared with the builder (see `shadowsim.cli.run`).

## Output formats

- **text** — short summary: algorithm, labels, resources, errors, saved/exported paths.
- **json** — the `run_page` payload (curves, resources, benchmark errors when comparing).
- **Disk** — `--save` and `--export` use the existing result-directory and metrics-JSON writers (metadata included for reproducibility). Seeds pass through catalog simulator/backend arguments such as `--seed`.

## Errors

Invalid model parameters, unknown catalog ids, missing extras, and illegal save paths print `error: …` on stderr and exit with status `1` (no traceback for those cases).

## Scope notes (issue #66)

This CLI intentionally reuses the builder pipeline rather than duplicating simulation logic. Deferred relative to the original issue:

- **Noise configuration** — no library noise-model API yet.
- **CSV export** — machine-readable stdout and on-disk JSON/NumPy cover reproducibility; CSV can be added later.
- **Hardware backends** — none exist today. Backend selection is always explicit; hardware must never become an implicit default if it is added later.
