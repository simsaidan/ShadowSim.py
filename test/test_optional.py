"""Tests for optional-extra imports."""

from unittest.mock import patch

import pytest

from shadowsim._optional import import_optional


def _missing(name: str | None, message: str = "missing"):
    def boom(_module: str):
        raise ModuleNotFoundError(message, name=name)

    return boom


def test_import_optional_returns_installed_module():
    module = import_optional("json", extra="qutip")
    assert module.loads("{}") == {}


def test_import_optional_names_missing_extra():
    with patch("shadowsim._optional.importlib.import_module", side_effect=_missing("qutip")):
        with pytest.raises(ImportError, match=r"pip install 'shadowsim\[qutip\]'") as exc_info:
            import_optional("shadowsim.simulators.qutip_simulator", extra="qutip")
    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)


def test_import_optional_uses_top_level_of_dotted_name():
    with patch("shadowsim._optional.importlib.import_module", side_effect=_missing("matplotlib.pyplot")):
        with pytest.raises(ImportError, match=r"shadowsim\[viz\]"):
            import_optional("matplotlib.pyplot", extra="viz")


def test_import_optional_reraises_unrelated_import_error():
    with patch("shadowsim._optional.importlib.import_module", side_effect=_missing("not_a_real_pkg")):
        with pytest.raises(ModuleNotFoundError, match="missing") as exc_info:
            import_optional("shadowsim.simulators.qutip_simulator", extra="qutip")
    assert "shadowsim[qutip]" not in str(exc_info.value)


def test_import_optional_reraises_when_import_name_is_missing():
    with patch("shadowsim._optional.importlib.import_module", side_effect=_missing(None, "failed without a name")):
        with pytest.raises(ModuleNotFoundError, match="failed without a name"):
            import_optional("json", extra="qutip")


def test_import_optional_unknown_extra_matches_its_own_name():
    with patch("shadowsim._optional.importlib.import_module", side_effect=_missing("customlib")):
        with pytest.raises(ImportError, match=r"shadowsim\[customlib\]"):
            import_optional("customlib", extra="customlib")
