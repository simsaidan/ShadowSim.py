"""Scaffold a new simulator backend (stub, export, and test)."""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_PASCAL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_SIMULATOR_IMPORT_RE = re.compile(
    r"^from\s+shadowsim\.simulators\.(\w+)\s+import\b",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SimulatorNames:
    """Derived names for a scaffolded simulator."""

    base_name: str
    class_name: str
    snake_name: str
    module_name: str
    simulator_id: str

    @property
    def stub_filename(self) -> str:
        """Return the stub module filename."""
        return f"{self.module_name}.py"

    @property
    def test_filename(self) -> str:
        """Return the scaffolded test filename."""
        return f"test_{self.module_name}.py"


class ScaffoldError(Exception):
    """Raised when simulator scaffolding cannot proceed."""


def pascal_to_snake(name: str) -> str:
    """Convert a PascalCase name to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def normalize_base_name(raw: str) -> str:
    """Validate PascalCase input and strip a trailing ``Simulator`` suffix."""
    name = raw.strip()
    if not name:
        raise ScaffoldError("Name must not be empty")
    if any(ch.isspace() for ch in name):
        raise ScaffoldError("Name must not contain spaces")
    if "_" in name or "-" in name:
        raise ScaffoldError("Name must be PascalCase with no underscores or hyphens")
    if not _PASCAL_RE.fullmatch(name):
        raise ScaffoldError("Name must be PascalCase (start with an uppercase letter; letters and digits only)")
    if name.endswith("Simulator") and name != "Simulator":
        name = name[: -len("Simulator")]
        # Defensive: unreachable after _PASCAL_RE, kept for clear errors if the regex changes.
        if not name or not _PASCAL_RE.fullmatch(name):  # pragma: no cover
            raise ScaffoldError("Name must include a PascalCase prefix before 'Simulator'")
    if name == "Simulator":
        raise ScaffoldError("Name 'Simulator' is reserved for the base class")
    return name


def derive_names(raw: str) -> SimulatorNames:
    """Derive class, module, and id names from a user-provided PascalCase name."""
    base = normalize_base_name(raw)
    snake = pascal_to_snake(base)
    module = f"{snake}_simulator"
    return SimulatorNames(
        base_name=base,
        class_name=f"{base}Simulator",
        snake_name=snake,
        module_name=module,
        simulator_id=module,
    )


def default_repo_root() -> Path:
    """Resolve the repository root from the working directory or package location."""
    cwd = Path.cwd()
    if (cwd / "shadowsim" / "simulators").is_dir():
        return cwd
    package_root = Path(__file__).resolve().parents[1]
    repo_root = package_root.parent
    if (repo_root / "shadowsim" / "simulators").is_dir():
        return repo_root
    raise ScaffoldError("Could not find the ShadowSim.py repository root. Run this command from the cloned repository.")


def stub_path(repo_root: Path, names: SimulatorNames) -> Path:
    """Return the path for the new simulator module."""
    return repo_root / "shadowsim" / "simulators" / names.stub_filename


def test_path(repo_root: Path, names: SimulatorNames) -> Path:
    """Return the path for the scaffolded simulator test."""
    return repo_root / "test" / "simulators" / names.test_filename


def init_path(repo_root: Path) -> Path:
    """Return the simulators package ``__init__.py`` path."""
    return repo_root / "shadowsim" / "simulators" / "__init__.py"


def check_collisions(repo_root: Path, names: SimulatorNames) -> None:
    """Raise if stub, test, or export already exist for this name."""
    stub = stub_path(repo_root, names)
    test = test_path(repo_root, names)
    init = init_path(repo_root)
    problems: list[str] = []

    if stub.exists():
        problems.append(f"simulator module already exists: {stub}")
    if test.exists():
        problems.append(f"test file already exists: {test}")
    if not init.exists():
        problems.append(f"simulators package init is missing: {init}")
    else:
        init_text = init.read_text(encoding="utf-8")
        if re.search(rf"\b{re.escape(names.class_name)}\b", init_text):
            problems.append(f"class already exported in {init}: {names.class_name}")
        elif re.search(
            rf"shadowsim\.simulators\.{re.escape(names.module_name)}\b",
            init_text,
        ):
            problems.append(f"module already imported in {init}: {names.module_name}")

    if problems:
        raise ScaffoldError("Name already exists:\n- " + "\n- ".join(problems))


def render_stub(names: SimulatorNames) -> str:
    """Return the source for a new simulator stub module."""
    return f'''"""{names.base_name} simulator backend stub."""

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.operator import Operator
from shadowsim.core.state import State
from shadowsim.simulators.simulator import Simulator


class {names.class_name}(Simulator):
    """Simulate quantum dynamics with {names.base_name}.

    TODO: replace this docstring with a real description of the backend.
    """

    def __init__(
        self,
        hamiltonians: list[Hamiltonian],
        lindblads: list[Operator],
        initial_state: State,
        num_qubits: int,
        total_time: float,
        time_steps: int,
    ):
        """Initialize a {names.class_name} for the given model."""
        super().__init__(
            hamiltonians,
            lindblads,
            initial_state,
            num_qubits,
            total_time,
            time_steps,
            "{names.simulator_id}",
        )

    def simulate(self):
        """Evolve the system and store expectation traces in ``self.results``."""
        # TODO: implement your simulator here
        raise NotImplementedError("TODO: implement your simulator here")

    def __str__(self):
        """Return a short string representation of the simulator."""
        return (
            "{names.class_name}("
            f"num_qubits={{self.num_qubits}}, "
            f"time_steps={{self.time_steps}}"
            ")"
        )

    def __repr__(self):
        """Return a detailed string representation of the simulator."""
        return (
            "{names.class_name}("
            f"hamiltonians={{self.hamiltonians!r}}, "
            f"lindblads={{self.lindblads!r}}, "
            f"initial_state={{self.initial_state!r}}, "
            f"num_qubits={{self.num_qubits}}, "
            f"total_time={{self.total_time}}, "
            f"time_steps={{self.time_steps}}"
            ")"
        )
'''


def render_test(names: SimulatorNames) -> str:
    """Return the source for a minimal simulator test scaffold."""
    return f'''import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, State
from shadowsim.simulators import {names.class_name}
from shadowsim.simulators.simulator import Simulator

Z = np.diag([1.0, -1.0]).astype(np.complex128)


def _tiny():
    return {names.class_name}(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        0.1,
        3,
    )


def test_{names.snake_name}_simulator_is_simulator():
    sim = _tiny()
    assert isinstance(sim, Simulator)
    assert sim.id == "{names.simulator_id}"


def test_{names.snake_name}_simulator_simulate_not_implemented():
    sim = _tiny()
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        sim.simulate()


def test_{names.snake_name}_simulator_str_and_repr():
    sim = _tiny()
    assert "{names.class_name}(" in str(sim)
    assert "num_qubits=1" in str(sim)
    assert "{names.class_name}(" in repr(sim)
    assert "time_steps=3" in repr(sim)
'''


def patch_init_file(path: Path, names: SimulatorNames) -> None:
    """Insert an alphabetical import for the new simulator into ``__init__.py``."""
    content = path.read_text(encoding="utf-8")
    if re.search(rf"\b{re.escape(names.class_name)}\b", content):
        raise ScaffoldError(f"class already exported in {path}: {names.class_name}")
    if re.search(rf"shadowsim\.simulators\.{re.escape(names.module_name)}\b", content):
        raise ScaffoldError(f"module already imported in {path}: {names.module_name}")

    new_line = f"from shadowsim.simulators.{names.module_name} import {names.class_name}"
    matches = list(_SIMULATOR_IMPORT_RE.finditer(content))
    if not matches:
        if content and not content.endswith("\n"):
            content += "\n"
        path.write_text(content + new_line + "\n", encoding="utf-8")
        return

    insert_at = None
    for match in matches:
        module = match.group(1)
        if names.module_name < module:
            insert_at = match.start()
            break
    if insert_at is None:
        last = matches[-1]
        # Advance past a possible multi-line import block.
        idx = last.end()
        while idx < len(content) and content[idx] != "\n":
            idx += 1
        if idx < len(content) and content[idx] == "\n":
            idx += 1
        depth = content[last.start() : idx].count("(") - content[last.start() : idx].count(")")
        while depth > 0 and idx < len(content):
            line_end = content.find("\n", idx)
            if line_end == -1:
                idx = len(content)
                break
            chunk = content[idx : line_end + 1]
            depth += chunk.count("(") - chunk.count(")")
            idx = line_end + 1
        insert_at = idx
        path.write_text(content[:insert_at] + new_line + "\n" + content[insert_at:], encoding="utf-8")
        return

    path.write_text(content[:insert_at] + new_line + "\n" + content[insert_at:], encoding="utf-8")


def create_simulator(raw_name: str, *, repo_root: Path | None = None) -> SimulatorNames:
    """Validate, check collisions, and write stub + export + test scaffold."""
    names = derive_names(raw_name)
    root = repo_root if repo_root is not None else default_repo_root()
    check_collisions(root, names)

    stub = stub_path(root, names)
    test = test_path(root, names)
    init = init_path(root)

    test.parent.mkdir(parents=True, exist_ok=True)
    init_before = init.read_text(encoding="utf-8")
    stub.write_text(render_stub(names), encoding="utf-8")
    try:
        patch_init_file(init, names)
        test.write_text(render_test(names), encoding="utf-8")
    except Exception:
        if stub.exists():
            stub.unlink()
        if init.read_text(encoding="utf-8") != init_before:
            init.write_text(init_before, encoding="utf-8")
        if test.exists():
            test.unlink()
        raise

    return names


def _prompt_name() -> str:
    """Ask the user for a PascalCase simulator name."""
    try:
        return input("Simulator name (PascalCase, no spaces): ").strip()
    except EOFError as exc:
        raise ScaffoldError("No name provided") from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="new-simulator",
        description="Scaffold a new ShadowSim simulator backend.",
    )
    parser.add_argument(
        "--name",
        help="PascalCase simulator name (e.g. WaveMatrix). Prompted if omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the new-simulator scaffolding CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw_name = args.name if args.name is not None else _prompt_name()
        names = create_simulator(raw_name)
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Created {names.class_name}")
    print(f"  module: shadowsim/simulators/{names.stub_filename}")
    print("  export: shadowsim/simulators/__init__.py")
    print(f"  test:   test/simulators/{names.test_filename}")
    print("Next: implement simulate() (look for TODO).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
