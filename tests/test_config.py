import json

import pytest

from app.core import config as config_mod
from app.core import secret
from app.core.models import AppConfig, ExcludeConfig, ExportOptions, Profile


@pytest.fixture(autouse=True)
def fake_secret(monkeypatch):
    """把 DPAPI 换成可逆假实现，保证测试跨平台可跑。"""
    monkeypatch.setattr(secret, "protect", lambda plain: ("ENC:" + plain) if plain else "")
    monkeypatch.setattr(secret, "unprotect", lambda token: token[4:])


def test_load_missing_file_returns_default(tmp_path):
    cfg, warnings = config_mod.load_config(tmp_path / "config.json")
    assert warnings == []
    assert cfg.active_profile == "default"
    assert cfg.profile().name == "default"


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    profile = Profile(
        name="dev", host="127.0.0.1", port=3307, user="u", password="p",
        databases={"db1": ExcludeConfig(["t1"], [".*_log$"])},
        selected_databases=["db1"],
        options=ExportOptions(batch_size=500),
    )
    cfg = AppConfig(active_profile="dev", profiles=[profile])
    config_mod.save_config(cfg, path)
    loaded, warnings = config_mod.load_config(path)
    assert warnings == []
    got = loaded.profile("dev")
    assert (got.host, got.port, got.user, got.password) == ("127.0.0.1", 3307, "u", "p")
    assert got.databases["db1"].exclude_tables == ["t1"]
    assert got.selected_databases == ["db1"]
    assert got.options.batch_size == 500
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_stores_encrypted_password(tmp_path):
    path = tmp_path / "config.json"
    config_mod.save_config(AppConfig(profiles=[Profile(name="dev", password="secret")]), path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["profiles"][0]["password_dpapi"] == "ENC:secret"


def test_corrupted_config_is_backed_up(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ not json", encoding="utf-8")
    cfg, warnings = config_mod.load_config(path)
    assert any("损坏" in w for w in warnings)
    assert cfg.profile() is not None
    assert list(tmp_path.glob("config.json.bak-*")), "坏配置应被备份"


def test_active_profile_is_repaired(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 1, "active_profile": "nope",
                                "profiles": [{"name": "dev"}]}), encoding="utf-8")
    cfg, _ = config_mod.load_config(path)
    assert cfg.active_profile == "dev"


def test_undecryptable_password_warns_and_clears(tmp_path, monkeypatch):
    def boom(token):
        raise secret.SecretError("bad")

    monkeypatch.setattr(secret, "unprotect", boom)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 1, "profiles": [
        {"name": "dev", "host": "h", "password_dpapi": "BAD"}]}), encoding="utf-8")
    cfg, warnings = config_mod.load_config(path)
    assert any("密码" in w for w in warnings)
    assert cfg.profile("dev").password == ""


def test_default_config_path_uses_override(tmp_path):
    target = tmp_path / "custom" / "cfg.json"
    assert config_mod.default_config_path(str(target)) == target.resolve()


def test_default_config_path_in_writable_dir(tmp_path):
    base = tmp_path / "portable"
    path = config_mod.default_config_path(None, base_dir=base)
    assert path == base.resolve() / "config.json"


def test_unknown_fields_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 1, "future_field": 1, "profiles": [
        {"name": "dev", "unknown": "x", "options": {"batch_size": 50}}]}), encoding="utf-8")
    cfg, warnings = config_mod.load_config(path)
    assert warnings == []
    assert cfg.profile("dev").options.batch_size == 50
