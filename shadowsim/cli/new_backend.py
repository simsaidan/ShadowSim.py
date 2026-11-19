"""Scaffold a new circuit backend (stub, export, and test)."""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_PASCAL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_RESERVED = frozenset({"Backend", "Circuit", "CircuitBackend"})
_EXPORTS_START_RE = re.compile(r"^_EXPORTS\b[^\n]*=\s*\{", re.MULTILINE)
_EXPORT_ENTRY_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r'"(?P<class_name>[A-Za-z_][A-Za-z0-9_]*)": '
    r'\("shadowsim\.backends\.(?P<module>\w+)", '
    r'(?P<extra>None|"[^"]*")\),$',
    re.MULTILINE,
)
_TYPE_CHECKING_RE = re.compile(r"^if TYPE_CHECKING:\n", re.MULTILINE)
_TYPE_IMPORT_RE = re.compile(
    r"^(?P<indent>[ \t]*)from shadowsim\.backends\.(?P<module>\w+) import "
    r"(?P<imported>[A-Za-z_][A-Za-z0-9_]*) as (?P=imported)$",
    re.MULTILINE,
)
_ALL_START_RE = re.compile(r"^__all__\s*=\s*\[", re.MULTILINE)
_ALL_ENTRY_RE = re.compile(
    r'^(?P<indent>[ \t]*)"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",$',
    re.MULTILINE,
)


@dataclass(frozen=True)
class BackendNames:
    """Derived names for a scaffolded circuit backend."""

    base_name: str
    class_name: str
    snake_name: str
    module_name: str
    backend_id: str

    @property
    def stub_filename(self) -> str:
        """Return the stub module filename."""
        return f"{self.module_name}.py"

    @property
    def test_filename(self) -> str:
        """Return the scaffolded test filename."""
        return f"test_{self.snake_name}_backend.py"


class ScaffoldError(Exception):
    """Raised when backend scaffolding cannot proceed."""


Kind = Literal["expectation", "sampling"]


def pascal_to_snake(name: str) -> str:
    """Convert a PascalCase name to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def normalize_base_name(raw: str) -> str:
    """Validate PascalCase input and strip a trailing backend suffix.

    ``CircuitBackend`` is removed first, then ``Backend``, so ``Cirq`` and
    ``CirqCircuitBackend`` both become ``Cirq``.

    Raises:
        ScaffoldError: ``raw`` is empty, not PascalCase, or a reserved name.
    """
    name = raw.strip()
    if not name:
        raise ScaffoldError("Name must not be empty")
    if any(ch.isspace() for ch in name):
        raise ScaffoldError("Name must not contain spaces")
    if "_" in name or "-" in name:
        raise ScaffoldError("Name must be PascalCase with no underscores or hyphens")
    if not _PASCAL_RE.fullmatch(name):
        raise ScaffoldError("Name must be PascalCase (start with an uppercase letter; letters and digits only)")
    if name.endswith("CircuitBackend") and name != "CircuitBackend":
        name = name[: -len("CircuitBackend")]
    elif name.endswith("Backend") and name != "Backend":
        name = name[: -len("Backend")]
    # Defensive: unreachable after _PASCAL_RE, kept for clear errors if the regex changes.
    if not name or not _PASCAL_RE.fullmatch(name):  # pragma: no cover
        raise ScaffoldError("Name must include a PascalCase prefix before 'Backend'")
    if name in _RESERVED:
        raise ScaffoldError(f"Name {name!r} is reserved")
    return name


def normalize_kind(raw: str) -> Kind:
    """Validate a backend kind.

    ``expectation`` stores no shot budget, the same shape as the NumPy backend.
    ``sampling`` stores ``shots``, the same shape as the Aer backend.

    Raises:
        ScaffoldError: ``raw`` is not ``expectation`` or ``sampling``.
    """
    kind = raw.strip().lower()
    if kind == "expectation":
        return "expectation"
    if kind == "sampling":
        return "sampling"
    raise ScaffoldError("Kind must be 'expectation' or 'sampling'")


def derive_names(raw: str) -> BackendNames:
    """Derive class, module, and catalog id from a PascalCase name.

    The catalog id is the class name with ``CircuitBackend`` and then
    ``Backend`` removed, lowercased. ``WaveMatrix`` becomes ``wavematrix``.
    """
    base = normalize_base_name(raw)
    snake = pascal_to_snake(base)
    return BackendNames(
        base_name=base,
        class_name=f"{base}CircuitBackend",
        snake_name=snake,
        module_name=snake,
        backend_id=base.lower(),
    )


def default_repo_root() -> Path:
    """Resolve the repository root from the working directory or package location.

    Raises:
        ScaffoldError: Neither location contains ``shadowsim/backends``.
    """
    cwd = Path.cwd()
    if (cwd / "shadowsim" / "backends").is_dir():
        return cwd
    package_root = Path(__file__).resolve().parents[1]
    repo_root = package_root.parent
    if (repo_root / "shadowsim" / "backends").is_dir():
        return repo_root
    raise ScaffoldError("Could not find the ShadowSim.py repository root. Run this command from the cloned repository.")


def stub_path(repo_root: Path, names: BackendNames) -> Path:
    """Return the path for the new backend module."""
    return repo_root / "shadowsim" / "backends" / names.stub_filename


def test_path(repo_root: Path, names: BackendNames) -> Path:
    """Return the path for the scaffolded backend test."""
    return repo_root / "test" / "backends" / names.test_filename


def init_path(repo_root: Path) -> Path:
    """Return the backends package ``__init__.py`` path."""
    return repo_root / "shadowsim" / "backends" / "__init__.py"


def _registration_conflict(text: str, path: Path, names: BackendNames) -> str | None:
    """Return an error message when ``names`` is already present in ``text``."""
    if re.search(rf"\b{re.escape(names.class_name)}\b", text):
        return f"class already exported in {path}: {names.class_name}"
    if re.search(rf"shadowsim\.backends\.{re.escape(names.module_name)}\b", text):
        return f"module already registered in {path}: {names.module_name}"
    return None


def check_collisions(repo_root: Path, names: BackendNames) -> None:
    """Raise if the stub, test, or export already exists for this name.

    Raises:
        ScaffoldError: A module, test, or export for ``names`` is already present,
            or the backends package init is missing.
    """
    stub = stub_path(repo_root, names)
    test = test_path(repo_root, names)
    init = init_path(repo_root)
    problems: list[str] = []

    if stub.exists():
        problems.append(f"backend module already exists: {stub}")
    if test.exists():
        problems.append(f"test file already exists: {test}")
    if not init.exists():
        problems.append(f"backends package init is missing: {init}")
    else:
        init_text = init.read_text(encoding="utf-8")
        conflict = _registration_conflict(init_text, init, names)
        if conflict is not None:
            problems.append(conflict)

    if problems:
        raise ScaffoldError("Name already exists:\n- " + "\n- ".join(problems))


def render_stub(names: BackendNames, *, kind: str = "expectation") -> str:
    """Return the source for a new backend stub module.

    ``expectation`` stores no shot budget. ``sampling`` stores ``shots``.

    Raises:
        ScaffoldError: ``kind`` is not ``expectation`` or ``sampling``.
    """
    resolved = normalize_kind(kind)
    if resolved == "sampling":
        return _render_sampling_stub(names)
    return _render_expectation_stub(names)


def render_test(names: BackendNames, *, kind: str = "expectation") -> str:
    """Return the source for a backend test that passes while the stub raises.

    Raises:
        ScaffoldError: ``kind`` is not ``expectation`` or ``sampling``.
    """
    resolved = normalize_kind(kind)
    if resolved == "sampling":
        return _render_sampling_test(names)
    return _render_expectation_test(names)


def _render_methods(names: BackendNames) -> str:
    """Return the three stub methods that still need an implementation."""
    return '''
    def run_counts(self, program: Program, *, shots: int, seed: int | None) -> dict[str, int]:
        """Sample ``program`` in the computational basis.

        Raises:
            NotImplementedError: The backend is still a stub.
        """
        del program, shots, seed
        raise NotImplementedError("TODO: implement your backend here")

    def z_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return ⟨Z⟩ for each qubit in ``qubits``.

        Raises:
            NotImplementedError: The backend is still a stub.
        """
        del program, qubits, shots, seed
        raise NotImplementedError("TODO: implement your backend here")

    def x_expectations(
        self,
        program: Program,
        qubits: Sequence[int],
        *,
        shots: int,
        seed: int | None,
    ) -> list[float]:
        """Return ⟨X⟩ for each qubit in ``qubits``.

        Raises:
            NotImplementedError: The backend is still a stub.
        """
        del program, qubits, shots, seed
        raise NotImplementedError("TODO: implement your backend here")
'''


def _render_expectation_stub(names: BackendNames) -> str:
    """Return the source for an expectation backend stub."""
    return f'''"""{names.base_name} circuit backend stub."""

from collections.abc import Sequence

from shadowsim.backends._arguments import _UnsupportedCircuitMetrics
from shadowsim.backends.program import Program


class {names.class_name}(_UnsupportedCircuitMetrics):
    """Run a program with {names.base_name}.

    TODO: replace this docstring with a real description of the backend.
    This backend stores no ``shots`` attribute, so Trotterization reads exact
    expectations once ``z_expectations`` and ``x_expectations`` are implemented.

    Attributes:
        name: ``"{names.backend_id}"``. Stored on simulation result metadata.
    """

    def __init__(self) -> None:
        """Record the {names.base_name} backend name."""
        self.name = "{names.backend_id}"
{_render_methods(names)}'''


def _render_sampling_stub(names: BackendNames) -> str:
    """Return the source for a sampling backend stub."""
    return f'''"""{names.base_name} circuit backend stub."""

from collections.abc import Sequence

from shadowsim.backends._arguments import _require_shots, _UnsupportedCircuitMetrics
from shadowsim.backends.program import Program


class {names.class_name}(_UnsupportedCircuitMetrics):
    """Run a program with {names.base_name} and return shot counts.

    TODO: replace this docstring with a real description of the backend.
    ``shots`` is the shot budget simulators pass to each run.

    Attributes:
        name: ``"{names.backend_id}"``. Stored on simulation result metadata.
        shots: Shot budget stored for simulators that sample.
    """

    def __init__(self, shots: int = 10000) -> None:
        """Store the shot budget.

        Args:
            shots: Number of shots for each circuit. Must be a positive integer.

        Raises:
            ValueError: ``shots`` is not a positive integer.
        """
        self.name = "{names.backend_id}"
        self.shots = _require_shots(shots)
{_render_methods(names)}'''


def _render_expectation_test(names: BackendNames) -> str:
    """Return the source for an expectation backend test."""
    return f'''import pytest

from shadowsim.backends import {names.class_name}
from shadowsim.backends.program import Program


def _backend():
    return {names.class_name}()


def test_{names.snake_name}_backend_name():
    backend = _backend()
    assert backend.name == "{names.backend_id}"
    assert not hasattr(backend, "shots")


def test_{names.snake_name}_backend_methods_not_implemented():
    backend = _backend()
    program = Program(1, 0, [])
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.run_counts(program, shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.z_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.x_expectations(program, [0], shots=1, seed=None)
'''


def _render_sampling_test(names: BackendNames) -> str:
    """Return the source for a sampling backend test."""
    return f'''import pytest

from shadowsim.backends import {names.class_name}
from shadowsim.backends.program import Program


def _backend():
    return {names.class_name}(shots=4)


def test_{names.snake_name}_backend_name():
    backend = _backend()
    assert backend.name == "{names.backend_id}"
    assert backend.shots == 4


def test_{names.snake_name}_backend_methods_not_implemented():
    backend = _backend()
    program = Program(1, 0, [])
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.run_counts(program, shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.z_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.x_expectations(program, [0], shots=1, seed=None)
'''


def _delimited_span(content: str, path: Path, opener: re.Pattern[str], close: str, label: str) -> tuple[int, int]:
    """Return the half-open span of a brace or bracket body opened by ``opener``."""
    match = opener.search(content)
    if match is None:
        raise ScaffoldError(f"backends package init has no {label}: {path}")
    open_char = "{" if close == "}" else "["
    depth = 1
    for idx in range(match.end(), len(content)):
        char = content[idx]
        if char == open_char:
            depth += 1
        elif char == close:
            depth -= 1
            if depth == 0:
                return match.end(), idx
    raise ScaffoldError(f"backends package init has an unclosed {label}: {path}")


def _type_checking_span(content: str, path: Path) -> tuple[int, int]:
    """Return the half-open span of the ``TYPE_CHECKING`` import block."""
    match = _TYPE_CHECKING_RE.search(content)
    if match is None:
        raise ScaffoldError(f"backends package init has no TYPE_CHECKING block: {path}")
    end = match.end()
    while end < len(content):
        newline = content.find("\n", end)
        line = content[end:] if newline == -1 else content[end:newline]
        if line.strip() and not line.startswith((" ", "\t")):
            break
        end = len(content) if newline == -1 else newline + 1
    return match.end(), end


def _insert_sorted(body: str, new_line: str, entries: list[re.Match[str]], new_key: str, key_group: str) -> str:
    """Return ``body`` with ``new_line`` inserted before the first later entry."""
    for entry in entries:
        if new_key < entry.group(key_group):
            insert_at = entry.start()
            return body[:insert_at] + new_line + "\n" + body[insert_at:]
    if entries:
        insert_at = entries[-1].end()
        if insert_at < len(body) and body[insert_at] == "\n":
            insert_at += 1
        return body[:insert_at] + new_line + "\n" + body[insert_at:]
    if body.endswith("\n"):
        return body + new_line + "\n"
    if body:
        return body + "\n" + new_line + "\n"
    return new_line + "\n"


def _export_line(names: BackendNames) -> str:
    """Return an ``_EXPORTS`` entry for a backend with no optional extra."""
    return f'    "{names.class_name}": ("shadowsim.backends.{names.module_name}", None),'


def _import_line(names: BackendNames) -> str:
    """Return a ``TYPE_CHECKING`` import for the new backend class."""
    return f"    from shadowsim.backends.{names.module_name} import {names.class_name} as {names.class_name}"


def _all_line(names: BackendNames) -> str:
    """Return an ``__all__`` entry for the new backend class."""
    return f'    "{names.class_name}",'


def patch_init_file(path: Path, names: BackendNames) -> None:
    """Register the new backend in ``_EXPORTS``, ``TYPE_CHECKING``, and ``__all__``.

    The extra is ``None``. ``_EXPORTS`` and the type-checking import are ordered
    by module name. ``__all__`` is ordered by class name.

    Raises:
        ScaffoldError: ``names`` is already registered, or a required block is
            missing or unclosed.
    """
    content = path.read_text(encoding="utf-8")
    conflict = _registration_conflict(content, path, names)
    if conflict is not None:
        raise ScaffoldError(conflict)
    exports_start, exports_end = _delimited_span(content, path, _EXPORTS_START_RE, "}", "_EXPORTS map")
    exports = _insert_sorted(
        content[exports_start:exports_end],
        _export_line(names),
        list(_EXPORT_ENTRY_RE.finditer(content[exports_start:exports_end])),
        names.module_name,
        "module",
    )
    content = content[:exports_start] + exports + content[exports_end:]
    typing_start, typing_end = _type_checking_span(content, path)
    typing = _insert_sorted(
        content[typing_start:typing_end],
        _import_line(names),
        list(_TYPE_IMPORT_RE.finditer(content[typing_start:typing_end])),
        names.module_name,
        "module",
    )
    content = content[:typing_start] + typing + content[typing_end:]
    all_start, all_end = _delimited_span(content, path, _ALL_START_RE, "]", "__all__ list")
    exported = _insert_sorted(
        content[all_start:all_end],
        _all_line(names),
        list(_ALL_ENTRY_RE.finditer(content[all_start:all_end])),
        names.class_name,
        "name",
    )
    path.write_text(content[:all_start] + exported + content[all_end:], encoding="utf-8")


def create_backend(
    raw_name: str,
    *,
    repo_root: Path | None = None,
    kind: str = "expectation",
) -> BackendNames:
    """Validate, check collisions, and write the stub, export, and test.

    ``kind="expectation"`` writes a backend with no ``shots`` attribute.
    ``kind="sampling"`` writes a backend that stores ``shots``. On failure the
    stub and test are removed and ``__init__.py`` is restored.

    Raises:
        ScaffoldError: The name or kind is invalid, or a file already exists.
    """
    names = derive_names(raw_name)
    resolved = normalize_kind(kind)
    root = repo_root if repo_root is not None else default_repo_root()
    check_collisions(root, names)

    stub = stub_path(root, names)
    test = test_path(root, names)
    init = init_path(root)

    test.parent.mkdir(parents=True, exist_ok=True)
    init_before = init.read_text(encoding="utf-8")
    stub.write_text(render_stub(names, kind=resolved), encoding="utf-8")
    try:
        patch_init_file(init, names)
        test.write_text(render_test(names, kind=resolved), encoding="utf-8")
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
    """Ask the user for a PascalCase backend name.

    Raises:
        ScaffoldError: Standard input is closed before a name is entered.
    """
    try:
        return input("Backend name (PascalCase, no spaces): ").strip()
    except EOFError as exc:
        raise ScaffoldError("No name provided") from exc


def _prompt_kind() -> Kind:
    """Ask whether the backend returns expectations or shot counts.

    Raises:
        ScaffoldError: Standard input is closed, or the answer is not a kind.
    """
    try:
        answer = input("Backend kind (expectation/sampling): ")
    except EOFError as exc:
        raise ScaffoldError("No kind provided") from exc
    return normalize_kind(answer)


def _scaffold_choices(args: argparse.Namespace) -> tuple[str, Kind]:
    """Return the name and kind for this invocation.

    A missing name or kind is read from the prompt. The name is validated
    before the kind is requested.
    """
    raw_name = args.name if args.name is not None else _prompt_name()
    derive_names(raw_name)
    kind = normalize_kind(args.kind) if args.kind is not None else _prompt_kind()
    return raw_name, kind


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="new-backend",
        description="Scaffold a new ShadowSim circuit backend.",
    )
    parser.add_argument(
        "--name",
        help="PascalCase backend name (e.g. Cirq). Prompted if omitted.",
    )
    parser.add_argument(
        "--kind",
        choices=["expectation", "sampling"],
        help="expectation stores no shot budget; sampling stores shots. Prompted if omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the new-backend scaffolding CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw_name, kind = _scaffold_choices(args)
        names = create_backend(raw_name, kind=kind)
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Created {names.class_name}")
    print(f"  kind:   {kind}")
    print(f"  id:     {names.backend_id}")
    print(f"  module: shadowsim/backends/{names.stub_filename}")
    print("  export: shadowsim/backends/__init__.py")
    print(f"  test:   test/backends/{names.test_filename}")
    print("Next: implement run_counts, z_expectations, and x_expectations (look for TODO).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
