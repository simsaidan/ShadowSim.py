"""Tests for the new-backend scaffolding CLI."""

import importlib.util
from pathlib import Path

import pytest

from shadowsim.backends.program import Program
from shadowsim.cli import new_backend as nb
from shadowsim.cli.new_backend import (
    ScaffoldError,
    check_collisions,
    create_backend,
    derive_names,
    main,
    normalize_base_name,
    patch_init_file,
    render_stub,
    render_test,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

_FAKE_INIT = """\
\"\"\"Circuit execution backends.\"\"\"

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shadowsim.backends.numpy import NumpyCircuitBackend as NumpyCircuitBackend
    from shadowsim.backends.qulacs import QulacsCircuitBackend as QulacsCircuitBackend

_EXPORTS: dict[str, tuple[str, str | None]] = {
    "NumpyCircuitBackend": ("shadowsim.backends.numpy", None),
    "QulacsCircuitBackend": ("shadowsim.backends.qulacs", "qulacs"),
}

__all__ = [
    "NumpyCircuitBackend",
    "QulacsCircuitBackend",
]
"""


def _fake_repo(tmp_path: Path) -> Path:
    backends = tmp_path / "shadowsim" / "backends"
    backends.mkdir(parents=True)
    (backends / "__init__.py").write_text(_FAKE_INIT, encoding="utf-8")
    return tmp_path


def _init(root: Path) -> Path:
    return root / "shadowsim" / "backends" / "__init__.py"


def _load(path: Path, module_name: str) -> object:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_rejects_invalid_names():
    with pytest.raises(ScaffoldError, match="empty"):
        normalize_base_name("")
    with pytest.raises(ScaffoldError, match="spaces"):
        normalize_base_name("Foo Bar")
    with pytest.raises(ScaffoldError, match="underscores or hyphens"):
        normalize_base_name("Foo_Bar")
    with pytest.raises(ScaffoldError, match="underscores or hyphens"):
        normalize_base_name("Foo-Bar")
    with pytest.raises(ScaffoldError, match="PascalCase"):
        normalize_base_name("cirq")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("Backend")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("Circuit")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("CircuitBackend")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("BackendBackend")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("CircuitCircuitBackend")


def test_derive_names_strips_backend_suffixes():
    cirq = derive_names("CirqCircuitBackend")
    assert cirq.base_name == "Cirq"
    assert cirq.class_name == "CirqCircuitBackend"
    assert cirq.module_name == "cirq"
    assert cirq.backend_id == "cirq"
    assert cirq.stub_filename == "cirq.py"
    assert cirq.test_filename == "test_cirq_backend.py"

    plain = derive_names("FooBackend")
    assert plain.base_name == "Foo"
    assert plain.class_name == "FooCircuitBackend"

    wave = derive_names("WaveMatrix")
    assert wave.snake_name == "wave_matrix"
    assert wave.backend_id == "wavematrix"
    assert wave.module_name == "wave_matrix"


def test_normalize_kind():
    assert nb.normalize_kind(" Expectation ") == "expectation"
    assert nb.normalize_kind("sampling") == "sampling"
    with pytest.raises(ScaffoldError, match="Kind must"):
        nb.normalize_kind("counts")


def test_default_repo_root_from_cwd(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)
    assert nb.default_repo_root() == root


def test_default_repo_root_from_package_location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert nb.default_repo_root() == REPO_ROOT


def test_default_repo_root_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "pkg" / "cli" / "new_backend.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("#", encoding="utf-8")
    monkeypatch.setattr(nb, "__file__", str(fake))
    with pytest.raises(ScaffoldError, match="Could not find"):
        nb.default_repo_root()


def test_existing_backend_name_collides_in_real_repo():
    with pytest.raises(ScaffoldError, match="already exists"):
        check_collisions(REPO_ROOT, derive_names("Numpy"))


def test_check_collisions_missing_init(tmp_path):
    (tmp_path / "shadowsim" / "backends").mkdir(parents=True)
    with pytest.raises(ScaffoldError, match="init is missing"):
        check_collisions(tmp_path, derive_names("Foo"))


def test_check_collisions_module_registered_without_class(tmp_path):
    root = _fake_repo(tmp_path)
    _init(root).write_text(
        "if TYPE_CHECKING:\n"
        "_EXPORTS: dict[str, tuple[str, str | None]] = {\n"
        '    "OtherThing": ("shadowsim.backends.foo", None),\n'
        "}\n"
        "__all__ = []\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="module already registered"):
        check_collisions(root, derive_names("Foo"))


def test_create_backend_writes_stub_init_and_test(tmp_path):
    root = _fake_repo(tmp_path)
    names = create_backend("Penny", repo_root=root)

    stub = root / "shadowsim" / "backends" / "penny.py"
    test = root / "test" / "backends" / "test_penny_backend.py"
    text = _init(root).read_text(encoding="utf-8")
    typing = text.split("if TYPE_CHECKING:", 1)[1].split("_EXPORTS", 1)[0]
    exports = text.split("_EXPORTS", 1)[1].split("__all__", 1)[0]
    all_body = text.split("__all__ = [", 1)[1].split("]", 1)[0]

    assert stub.is_file()
    assert test.is_file()
    assert names.class_name == "PennyCircuitBackend"
    assert '"PennyCircuitBackend": ("shadowsim.backends.penny", None),' in exports
    assert typing.index("numpy") < typing.index("penny") < typing.index("qulacs")
    assert exports.index("numpy") < exports.index("penny") < exports.index("qulacs")
    assert all_body.index("NumpyCircuitBackend") < all_body.index("PennyCircuitBackend")
    assert all_body.index("PennyCircuitBackend") < all_body.index("QulacsCircuitBackend")
    assert 'not hasattr(backend, "shots")' in test.read_text(encoding="utf-8")


def test_create_backend_uses_the_working_directory(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)
    create_backend("Foo")
    assert (root / "shadowsim" / "backends" / "foo.py").is_file()


def test_second_create_fails_without_changes(tmp_path):
    root = _fake_repo(tmp_path)
    create_backend("Foo", repo_root=root)
    stub = root / "shadowsim" / "backends" / "foo.py"
    test = root / "test" / "backends" / "test_foo_backend.py"
    init = _init(root)
    before_stub = stub.read_text(encoding="utf-8")
    before_test = test.read_text(encoding="utf-8")
    before_init = init.read_text(encoding="utf-8")

    with pytest.raises(ScaffoldError, match="already exists"):
        create_backend("Foo", repo_root=root)

    assert stub.read_text(encoding="utf-8") == before_stub
    assert test.read_text(encoding="utf-8") == before_test
    assert init.read_text(encoding="utf-8") == before_init


def test_create_backend_rejects_unknown_kind(tmp_path):
    root = _fake_repo(tmp_path)
    with pytest.raises(ScaffoldError, match="Kind must"):
        create_backend("Foo", repo_root=root, kind="counts")
    assert not (root / "shadowsim" / "backends" / "foo.py").exists()


def test_generated_expectation_stub_imports_and_raises(tmp_path):
    root = _fake_repo(tmp_path)
    create_backend("Bar", repo_root=root, kind="expectation")
    module = _load(root / "shadowsim" / "backends" / "bar.py", "bar_backend_scaffold")
    backend = module.BarCircuitBackend()
    program = Program(1, 0, [])

    assert backend.name == "bar"
    assert not hasattr(backend, "shots")
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.run_counts(program, shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.z_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.x_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="does not support circuit metrics"):
        backend.depth(program)


def test_generated_sampling_stub_stores_shots(tmp_path):
    root = _fake_repo(tmp_path)
    create_backend("Bar", repo_root=root, kind="sampling")
    stub = (root / "shadowsim" / "backends" / "bar.py").read_text(encoding="utf-8")
    test = (root / "test" / "backends" / "test_bar_backend.py").read_text(encoding="utf-8")
    module = _load(root / "shadowsim" / "backends" / "bar.py", "bar_sampling_scaffold")
    program = Program(1, 0, [])

    assert "shots: int = 10000" in stub
    assert "_require_shots" in stub
    assert "backend.shots == 4" in test
    backend = module.BarCircuitBackend(shots=4)
    assert backend.name == "bar"
    assert backend.shots == 4
    assert module.BarCircuitBackend().shots == 10000
    with pytest.raises(ValueError, match="positive integer"):
        module.BarCircuitBackend(shots=0)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.run_counts(program, shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.z_expectations(program, [0], shots=1, seed=None)
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        backend.x_expectations(program, [0], shots=1, seed=None)


def test_render_rejects_unknown_kind():
    names = derive_names("Foo")
    with pytest.raises(ScaffoldError, match="Kind must"):
        render_stub(names, kind="counts")
    with pytest.raises(ScaffoldError, match="Kind must"):
        render_test(names, kind="counts")


def test_render_stub_contains_todo():
    text = render_stub(derive_names("Demo"))
    assert "TODO: replace this docstring" in text
    assert 'raise NotImplementedError("TODO: implement your backend here")' in text
    assert 'self.name = "demo"' in text
    assert "self.shots" not in text


def test_patch_init_rejects_duplicate_export(tmp_path):
    root = _fake_repo(tmp_path)
    with pytest.raises(ScaffoldError, match="already exported"):
        patch_init_file(_init(root), derive_names("Numpy"))


def test_patch_init_rejects_duplicate_module(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n"
        "_EXPORTS: dict[str, tuple[str, str | None]] = {\n"
        '    "OtherThing": ("shadowsim.backends.foo", None),\n'
        "}\n"
        "__all__ = []\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="module already registered"):
        patch_init_file(init, derive_names("Foo"))


def test_patch_init_requires_exports_map(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text('"""Empty package."""\n', encoding="utf-8")
    with pytest.raises(ScaffoldError, match="no _EXPORTS"):
        patch_init_file(init, derive_names("Alpha"))


def test_patch_init_rejects_unclosed_exports_map(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "_EXPORTS: dict[str, tuple[str, str | None]] = {\n"
        '    "NumpyCircuitBackend": ("shadowsim.backends.numpy", None),\n',
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="unclosed _EXPORTS"):
        patch_init_file(init, derive_names("Alpha"))


def test_patch_init_requires_type_checking_block(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "_EXPORTS: dict[str, tuple[str, str | None]] = {\n}\n__all__ = []\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="no TYPE_CHECKING"):
        patch_init_file(init, derive_names("Alpha"))


def test_patch_init_requires_all_list(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n_EXPORTS: dict[str, tuple[str, str | None]] = {\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="no __all__"):
        patch_init_file(init, derive_names("Alpha"))


def test_patch_init_rejects_unclosed_all_list(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n_EXPORTS: dict[str, tuple[str, str | None]] = {\n}\n__all__ = [\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="unclosed __all__"):
        patch_init_file(init, derive_names("Alpha"))


def test_patch_init_inserts_into_empty_blocks(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n\n_EXPORTS: dict[str, tuple[str, str | None]] = {\n}\n__all__ = [\n]\n",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Alpha"))
    text = init.read_text(encoding="utf-8")
    assert '"AlphaCircuitBackend": ("shadowsim.backends.alpha", None),' in text
    assert "from shadowsim.backends.alpha import AlphaCircuitBackend as AlphaCircuitBackend" in text
    assert '"AlphaCircuitBackend",' in text
    compile(text, str(init), "exec")


def test_patch_init_inserts_into_single_line_empty_blocks(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n_EXPORTS: dict[str, tuple[str, str | None]] = {}\n__all__ = []\n",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Alpha"))
    text = init.read_text(encoding="utf-8")
    entry = '"AlphaCircuitBackend": ("shadowsim.backends.alpha", None),'
    assert text.index("{") < text.index(entry) < text.index("}")
    assert text.index("__all__ = [") < text.index('"AlphaCircuitBackend",')
    compile(text, str(init), "exec")


def test_patch_init_inserts_before_later_module(tmp_path):
    root = _fake_repo(tmp_path)
    patch_init_file(_init(root), derive_names("Aer"))
    text = _init(root).read_text(encoding="utf-8")
    typing = text.split("if TYPE_CHECKING:", 1)[1].split("_EXPORTS", 1)[0]
    exports = text.split("_EXPORTS", 1)[1].split("__all__", 1)[0]
    all_body = text.split("__all__ = [", 1)[1].split("]", 1)[0]
    assert typing.index("aer") < typing.index("numpy")
    assert exports.index("aer") < exports.index("numpy")
    assert all_body.index("AerCircuitBackend") < all_body.index("NumpyCircuitBackend")


def test_patch_init_inserts_after_last_module(tmp_path):
    root = _fake_repo(tmp_path)
    patch_init_file(_init(root), derive_names("Zebra"))
    text = _init(root).read_text(encoding="utf-8")
    typing = text.split("if TYPE_CHECKING:", 1)[1].split("_EXPORTS", 1)[0]
    exports = text.split("_EXPORTS", 1)[1].split("__all__", 1)[0]
    all_body = text.split("__all__ = [", 1)[1].split("]", 1)[0]
    assert typing.index("qulacs") < typing.index("zebra")
    assert exports.index("qulacs") < exports.index("zebra")
    assert all_body.index("QulacsCircuitBackend") < all_body.index("ZebraCircuitBackend")


def test_patch_init_scans_nested_braces(tmp_path):
    root = _fake_repo(tmp_path)
    init = _init(root)
    init.write_text(
        "if TYPE_CHECKING:\n"
        "    from shadowsim.backends.qulacs import QulacsCircuitBackend as QulacsCircuitBackend\n"
        "_EXPORTS: dict[str, tuple[str, str | None]] = {\n"
        "    # {nested}\n"
        '    "QulacsCircuitBackend": ("shadowsim.backends.qulacs", "qulacs"),\n'
        "}\n"
        "__all__ = [\n"
        "    # [nested]\n"
        '    "QulacsCircuitBackend",\n'
        "]\n",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Alpha"))
    text = init.read_text(encoding="utf-8")
    assert text.index("alpha") < text.index("qulacs")
    assert text.index("AlphaCircuitBackend") < text.index("QulacsCircuitBackend")


def test_insert_sorted_without_trailing_newline():
    body = '    "AaaCircuitBackend": ("shadowsim.backends.aaa", None),'
    entries = list(nb._EXPORT_ENTRY_RE.finditer(body))
    text = nb._insert_sorted(body, nb._export_line(derive_names("Zebra")), entries, "zebra", "module")
    assert text.index("aaa") < text.index("zebra")
    assert 'None),    "ZebraCircuitBackend"' in text


def test_insert_sorted_nonempty_body_without_entries():
    text = nb._insert_sorted("    # note", nb._all_line(derive_names("Alpha")), [], "AlphaCircuitBackend", "name")
    assert text == '    # note\n    "AlphaCircuitBackend",\n'


def test_type_checking_span_edges():
    empty = "if TYPE_CHECKING:\n"
    start, end = nb._type_checking_span(empty, Path("init.py"))
    assert start == end

    indented = "if TYPE_CHECKING:\n    from shadowsim.backends.numpy import NumpyCircuitBackend as NumpyCircuitBackend"
    start, end = nb._type_checking_span(indented, Path("init.py"))
    assert "NumpyCircuitBackend" in indented[start:end]

    stopped = "if TYPE_CHECKING:\ncode"
    start, end = nb._type_checking_span(stopped, Path("init.py"))
    assert stopped[start:end] == ""

    with pytest.raises(ScaffoldError, match="no TYPE_CHECKING"):
        nb._type_checking_span("x = 1\n", Path("init.py"))


def test_create_rolls_back_when_patch_fails(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    init = _init(root)
    before_init = init.read_text(encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("patch failed")

    monkeypatch.setattr(nb, "patch_init_file", _boom)
    with pytest.raises(RuntimeError, match="patch failed"):
        create_backend("Rollback", repo_root=root)

    assert not (root / "shadowsim" / "backends" / "rollback.py").exists()
    assert not (root / "test" / "backends" / "test_rollback_backend.py").exists()
    assert init.read_text(encoding="utf-8") == before_init


def test_create_rollback_skips_missing_stub(tmp_path, monkeypatch):
    """Cover the stub.exists() false branch during rollback cleanup."""
    root = _fake_repo(tmp_path)
    real_write = Path.write_text

    def _write(self, data, encoding=None, errors=None, newline=None):
        kwargs = {"encoding": encoding, "errors": errors, "newline": newline}
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if self.parent.name == "backends" and self.suffix == ".py" and self.name != "__init__.py":
            return None
        return real_write(self, data, **kwargs)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("patch failed")

    monkeypatch.setattr(Path, "write_text", _write)
    monkeypatch.setattr(nb, "patch_init_file", _boom)
    with pytest.raises(RuntimeError, match="patch failed"):
        create_backend("Ghost", repo_root=root)

    assert not (root / "shadowsim" / "backends" / "ghost.py").exists()


def test_create_rolls_back_when_test_write_fails(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    init = _init(root)
    before_init = init.read_text(encoding="utf-8")
    real_write = Path.write_text

    def _write(self, data, encoding=None, errors=None, newline=None):
        kwargs = {"encoding": encoding, "errors": errors, "newline": newline}
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if self.name.startswith("test_") and self.suffix == ".py":
            real_write(self, data, **kwargs)
            raise OSError("fail after writing test")
        return real_write(self, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", _write)
    with pytest.raises(OSError, match="fail after writing test"):
        create_backend("Partial", repo_root=root)

    assert not (root / "shadowsim" / "backends" / "partial.py").exists()
    assert not (root / "test" / "backends" / "test_partial_backend.py").exists()
    assert init.read_text(encoding="utf-8") == before_init


def test_main_rejects_invalid_name(capsys):
    assert main(["--name", "not-valid"]) == 1
    assert "error:" in capsys.readouterr().err


def test_main_prompts_for_name_and_kind(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)
    prompts: list[str] = []
    answers = iter(["Prompted", "expectation"])

    def _input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", _input)
    assert main([]) == 0
    assert prompts == [
        "Backend name (PascalCase, no spaces): ",
        "Backend kind (expectation/sampling): ",
    ]
    out = capsys.readouterr().out
    assert "Created PromptedCircuitBackend" in out
    assert "kind:   expectation" in out
    assert "id:     prompted" in out
    assert "module: shadowsim/backends/prompted.py" in out
    assert "export: shadowsim/backends/__init__.py" in out
    assert "test:   test/backends/test_prompted_backend.py" in out
    assert "run_counts, z_expectations, and x_expectations" in out
    assert (root / "shadowsim" / "backends" / "prompted.py").is_file()


def test_main_sampling_from_flags(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)
    assert main(["--name", "ShotReader", "--kind", "sampling"]) == 0
    out = capsys.readouterr().out
    assert "Created ShotReaderCircuitBackend" in out
    assert "kind:   sampling" in out
    assert "id:     shotreader" in out
    stub = (root / "shadowsim" / "backends" / "shot_reader.py").read_text(encoding="utf-8")
    assert "shots: int = 10000" in stub


def test_prompt_name_eof(monkeypatch):
    def _eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    with pytest.raises(ScaffoldError, match="No name provided"):
        nb._prompt_name()


def test_main_kind_eof(monkeypatch, capsys):
    def _eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert main(["--name", "Ode"]) == 1
    assert "No kind provided" in capsys.readouterr().err


def test_main_rejects_bad_kind(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt: "counts")
    assert main(["--name", "Ode"]) == 1
    assert "Kind must" in capsys.readouterr().err
