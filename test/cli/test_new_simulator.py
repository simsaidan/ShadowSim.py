"""Tests for the new-simulator scaffolding CLI."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from shadowsim.cli import new_simulator as ns
from shadowsim.cli.new_simulator import (
    ScaffoldError,
    check_collisions,
    create_simulator,
    derive_names,
    main,
    normalize_base_name,
    patch_init_file,
    render_stub,
)
from shadowsim.core import Hamiltonian, State

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_repo(tmp_path: Path) -> Path:
    simulators = tmp_path / "shadowsim" / "simulators"
    simulators.mkdir(parents=True)
    (tmp_path / "test" / "simulators").mkdir(parents=True)
    (simulators / "__init__.py").write_text(
        '"""Quantum simulator implementations."""\n\n'
        "from shadowsim.simulators.qutip_simulator import QutipSimulator\n"
        "from shadowsim.simulators.simulator import Simulator\n"
        "from shadowsim.simulators.splitjmatrix_simulator import SplitJMatrixSimulator\n",
        encoding="utf-8",
    )
    return tmp_path


def test_normalize_rejects_invalid_names():
    with pytest.raises(ScaffoldError, match="empty"):
        normalize_base_name("")
    with pytest.raises(ScaffoldError, match="spaces"):
        normalize_base_name("Foo Bar")
    with pytest.raises(ScaffoldError, match="underscores or hyphens"):
        normalize_base_name("Foo_Bar")
    with pytest.raises(ScaffoldError, match="PascalCase"):
        normalize_base_name("trotterization")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("Simulator")
    with pytest.raises(ScaffoldError, match="reserved"):
        normalize_base_name("SimulatorSimulator")


def test_derive_names_strips_simulator_suffix():
    names = derive_names("TrotterizationSimulator")
    assert names.base_name == "Trotterization"
    assert names.class_name == "TrotterizationSimulator"
    assert names.module_name == "trotterization_simulator"
    assert names.simulator_id == "trotterization_simulator"


def test_default_repo_root_from_cwd(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)
    assert ns.default_repo_root() == root


def test_default_repo_root_from_package_location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ns.default_repo_root() == REPO_ROOT


def test_default_repo_root_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "pkg" / "cli" / "new_simulator.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("#", encoding="utf-8")
    monkeypatch.setattr(ns, "__file__", str(fake))
    with pytest.raises(ScaffoldError, match="Could not find"):
        ns.default_repo_root()


def test_existing_backend_name_collides_in_real_repo():
    names = derive_names("Qutip")
    with pytest.raises(ScaffoldError, match="already exists"):
        check_collisions(REPO_ROOT, names)


def test_check_collisions_missing_init(tmp_path):
    (tmp_path / "shadowsim" / "simulators").mkdir(parents=True)
    (tmp_path / "test" / "simulators").mkdir(parents=True)
    with pytest.raises(ScaffoldError, match="init is missing"):
        check_collisions(tmp_path, derive_names("Foo"))


def test_check_collisions_module_imported_without_class(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    init.write_text(
        "from shadowsim.simulators.foo_simulator import OtherThing\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="module already imported"):
        check_collisions(root, derive_names("Foo"))


def test_create_simulator_writes_stub_init_and_test(tmp_path):
    root = _fake_repo(tmp_path)
    names = create_simulator("Trotterization", repo_root=root)

    stub = root / "shadowsim" / "simulators" / "trotterization_simulator.py"
    test = root / "test" / "simulators" / "test_trotterization_simulator.py"
    init_text = (root / "shadowsim" / "simulators" / "__init__.py").read_text(encoding="utf-8")

    assert stub.is_file()
    assert test.is_file()
    assert "from shadowsim.simulators.trotterization_simulator import TrotterizationSimulator" in init_text
    # Alphabetical by module name: after splitjmatrix.
    assert init_text.index("splitjmatrix_simulator") < init_text.index("trotterization_simulator")
    assert names.class_name == "TrotterizationSimulator"


def test_second_create_fails_without_changes(tmp_path):
    root = _fake_repo(tmp_path)
    create_simulator("Foo", repo_root=root)
    stub = root / "shadowsim" / "simulators" / "foo_simulator.py"
    init = root / "shadowsim" / "simulators" / "__init__.py"
    before_stub = stub.read_text(encoding="utf-8")
    before_init = init.read_text(encoding="utf-8")

    with pytest.raises(ScaffoldError, match="already exists"):
        create_simulator("Foo", repo_root=root)

    assert stub.read_text(encoding="utf-8") == before_stub
    assert init.read_text(encoding="utf-8") == before_init


def test_generated_stub_imports_and_raises(tmp_path):
    root = _fake_repo(tmp_path)
    create_simulator("Bar", repo_root=root)
    stub = root / "shadowsim" / "simulators" / "bar_simulator.py"

    spec = importlib.util.spec_from_file_location("bar_simulator_scaffold", stub)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = module.BarSimulator

    z = np.diag([1.0, -1.0]).astype(np.complex128)
    sim = cls(
        [Hamiltonian(z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        0.1,
        3,
    )
    assert sim.id == "bar_simulator"
    with pytest.raises(NotImplementedError, match="TODO: implement"):
        sim.simulate()
    assert "BarSimulator(" in str(sim)
    assert "BarSimulator(" in repr(sim)


def test_patch_init_rejects_duplicate_export(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    names = derive_names("Qutip")
    with pytest.raises(ScaffoldError, match="already exported"):
        patch_init_file(init, names)


def test_patch_init_rejects_duplicate_module(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    init.write_text(
        "from shadowsim.simulators.foo_simulator import OtherThing\n",
        encoding="utf-8",
    )
    with pytest.raises(ScaffoldError, match="module already imported"):
        patch_init_file(init, derive_names("Foo"))


def test_patch_init_appends_when_no_simulator_imports(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    init.write_text('"""Empty package."""', encoding="utf-8")  # no trailing newline
    patch_init_file(init, derive_names("Alpha"))
    text = init.read_text(encoding="utf-8")
    assert text.endswith("from shadowsim.simulators.alpha_simulator import AlphaSimulator\n")


def test_patch_init_appends_when_init_already_newline_terminated(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    init.write_text('"""Empty package."""\n', encoding="utf-8")
    patch_init_file(init, derive_names("Alpha"))
    text = init.read_text(encoding="utf-8")
    assert text.endswith("from shadowsim.simulators.alpha_simulator import AlphaSimulator\n")


def test_patch_init_after_multiline_import(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    # No trailing newline: exercises EOF handling in the multi-line walker.
    init.write_text(
        "from shadowsim.simulators.splitjmatrix_simulator import (\n"
        "    SplitJMatrixSimulator,\n"
        "    cavity_population,\n"
        ")",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Zebra"))
    text = init.read_text(encoding="utf-8")
    assert "ZebraSimulator" in text
    assert text.index("splitjmatrix_simulator") < text.index("zebra_simulator")


def test_patch_init_after_multiline_import_with_trailing_newline(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    init.write_text(
        "from shadowsim.simulators.splitjmatrix_simulator import (\n"
        "    SplitJMatrixSimulator,\n"
        "    cavity_population,\n"
        ")\n",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Zebra"))
    text = init.read_text(encoding="utf-8")
    assert text.index("splitjmatrix_simulator") < text.index("zebra_simulator")


def test_patch_init_appends_after_single_line_import_at_eof(tmp_path):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    # Single-line import with no trailing newline: idx lands at EOF in the walker.
    init.write_text(
        "from shadowsim.simulators.aaa_simulator import AaaSimulator",
        encoding="utf-8",
    )
    patch_init_file(init, derive_names("Zzz"))
    text = init.read_text(encoding="utf-8")
    assert text.index("aaa_simulator") < text.index("zzz_simulator")


def test_create_rolls_back_when_patch_fails(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
    before_init = init.read_text(encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("patch failed")

    monkeypatch.setattr(ns, "patch_init_file", _boom)
    with pytest.raises(RuntimeError, match="patch failed"):
        create_simulator("Rollback", repo_root=root)

    stub = root / "shadowsim" / "simulators" / "rollback_simulator.py"
    test = root / "test" / "simulators" / "test_rollback_simulator.py"
    assert not stub.exists()
    assert not test.exists()
    assert init.read_text(encoding="utf-8") == before_init


def test_create_rollback_skips_missing_stub(tmp_path, monkeypatch):
    """Cover the stub.exists() false branch during rollback cleanup."""
    root = _fake_repo(tmp_path)
    real_write = Path.write_text

    def _write(self, data, encoding=None, errors=None, newline=None):
        kwargs = {"encoding": encoding, "errors": errors, "newline": newline}
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if self.parent.name == "simulators" and self.name.endswith("_simulator.py"):
            return None
        return real_write(self, data, **kwargs)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("patch failed")

    monkeypatch.setattr(Path, "write_text", _write)
    monkeypatch.setattr(ns, "patch_init_file", _boom)
    with pytest.raises(RuntimeError, match="patch failed"):
        create_simulator("Ghost", repo_root=root)

    assert not (root / "shadowsim" / "simulators" / "ghost_simulator.py").exists()


def test_create_rolls_back_when_test_write_fails(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path)
    init = root / "shadowsim" / "simulators" / "__init__.py"
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
        create_simulator("Partial", repo_root=root)

    stub = root / "shadowsim" / "simulators" / "partial_simulator.py"
    test = root / "test" / "simulators" / "test_partial_simulator.py"
    assert not stub.exists()
    assert not test.exists()
    assert init.read_text(encoding="utf-8") == before_init


def test_main_rejects_invalid_name(capsys):
    assert main(["--name", "not-valid"]) == 1
    err = capsys.readouterr().err
    assert "error:" in err


def test_main_prompts_for_name(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path)

    def _create(raw_name, *, repo_root=None):
        return create_simulator(raw_name, repo_root=root)

    monkeypatch.setattr(ns, "create_simulator", _create)
    monkeypatch.setattr("builtins.input", lambda _prompt: "Prompted")
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Created PromptedSimulator" in out


def test_prompt_name_eof(monkeypatch):
    def _eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    with pytest.raises(ScaffoldError, match="No name provided"):
        ns._prompt_name()


def test_main_success_on_fake_repo(tmp_path, monkeypatch, capsys):
    root = _fake_repo(tmp_path)
    monkeypatch.chdir(root)

    def _create(raw_name, *, repo_root=None):
        return create_simulator(raw_name, repo_root=root)

    monkeypatch.setattr(ns, "create_simulator", _create)
    assert main(["--name", "Baz"]) == 0
    out = capsys.readouterr().out
    assert "Created BazSimulator" in out
    assert (root / "shadowsim" / "simulators" / "baz_simulator.py").is_file()


def test_render_stub_contains_todo():
    text = render_stub(derive_names("Demo"))
    assert "# TODO: implement your simulator here" in text
    assert 'raise NotImplementedError("TODO: implement your simulator here")' in text
