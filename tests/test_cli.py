from app import __version__
from app.cli import main


def test_version_returns_zero(capsys):
    assert main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_selftest_returns_zero(monkeypatch, tmp_path):
    monkeypatch.setattr("app.selftest.selftest_log_path", lambda: tmp_path / "selftest.log")
    assert main(["--selftest"]) == 0
    assert "SELFTEST OK" in (tmp_path / "selftest.log").read_text(encoding="utf-8")


def test_dry_run_without_config_returns_two(monkeypatch, tmp_path):
    monkeypatch.setattr("app.cli.config_mod.default_config_path",
                        lambda override=None: tmp_path / "missing.json")
    assert main(["--dry-run"]) == 2


def test_unknown_operation_returns_two(capsys):
    assert main(["--config", "x.json"]) == 2
    assert "GUI 模式" in capsys.readouterr().out
