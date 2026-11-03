"""config.json：路径解析、读写、默认值、原子写、坏文件自愈。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from . import secret
from .models import AppConfig, ExcludeConfig, ExportOptions, Profile, UiState

CONFIG_VERSION = 1
CONFIG_FILENAME = "config.json"
APP_DIR_NAME = "MysqlExportTool"


def exe_dir() -> Path:
    """打包后是 exe 所在目录，开发时是项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-"):
            return True
    except OSError:
        return False


def default_config_path(override: str | None = None, base_dir: Path | None = None) -> Path:
    """--config > exe 同目录（可写）> %APPDATA%\\MysqlExportTool。"""
    if override:
        return Path(override).expanduser().resolve()
    base = Path(base_dir) if base_dir else exe_dir()
    if _dir_writable(base):
        return base.resolve() / CONFIG_FILENAME
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / APP_DIR_NAME / CONFIG_FILENAME


def default_export_dir(base_dir: Path | None = None) -> Path:
    """默认输出目录：exe 同目录 exports/，不可写时回退到文档目录。"""
    base = Path(base_dir) if base_dir else exe_dir()
    if _dir_writable(base):
        return base.resolve() / "exports"
    return Path.home() / "Documents" / APP_DIR_NAME / "exports"


def new_default_config() -> AppConfig:
    return AppConfig(version=CONFIG_VERSION, active_profile="default",
                     profiles=[Profile(name="default")])


def ensure_active_profile(config: AppConfig) -> None:
    """保证 active_profile 指向存在的 profile。"""
    names = [item.name for item in config.profiles]
    if not names:
        config.profiles = [Profile(name="default")]
        config.active_profile = "default"
    elif config.active_profile not in names:
        config.active_profile = names[0]


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _backup_broken(path: Path) -> Path:
    backup = path.with_name("%s.bak-%s" % (path.name, time.strftime("%Y%m%d_%H%M%S")))
    try:
        path.replace(backup)
    except OSError:
        pass
    return backup


def _profile_from_dict(raw: dict[str, Any], warnings: list[str]) -> Profile:
    profile = Profile(
        name=str(raw.get("name") or "default"),
        dialect=str(raw.get("dialect") or "mysql"),
        host=str(raw.get("host") or ""),
        port=_as_int(raw.get("port"), 3306),
        user=str(raw.get("user") or ""),
        charset=str(raw.get("charset") or "utf8mb4"),
        connect_timeout=_as_int(raw.get("connect_timeout"), 10),
        options=ExportOptions.from_dict(raw.get("options")),
    )
    token = raw.get("password_dpapi")
    if isinstance(token, str) and token:
        try:
            profile.password = secret.unprotect(token)
        except secret.SecretError:
            warnings.append("配置 %s 的密码无法解密，请重新输入密码" % profile.name)
    databases = raw.get("databases")
    if isinstance(databases, dict):
        profile.databases = {
            str(db): ExcludeConfig.from_dict(cfg) for db, cfg in databases.items()}
    selected = raw.get("selected_databases")
    if isinstance(selected, list):
        profile.selected_databases = [str(x) for x in selected]
    return profile


def _profile_to_dict(profile: Profile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "dialect": profile.dialect,
        "host": profile.host,
        "port": profile.port,
        "user": profile.user,
        "password_dpapi": secret.protect(profile.password) if profile.password else "",
        "charset": profile.charset,
        "connect_timeout": profile.connect_timeout,
        "databases": {db: cfg.to_dict() for db, cfg in profile.databases.items()},
        "selected_databases": list(profile.selected_databases),
        "options": profile.options.to_dict(),
    }


def load_config(path: Path) -> tuple[AppConfig, list[str]]:
    """读取配置；文件损坏时备份并重建默认配置。"""
    path = Path(path)
    warnings: list[str] = []
    if not path.exists():
        return new_default_config(), warnings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("配置文件根节点不是对象")
    except Exception as exc:
        backup = _backup_broken(path)
        warnings.append("配置文件损坏（%s），已备份为 %s 并重建默认配置" % (exc, backup.name))
        return new_default_config(), warnings

    config = new_default_config()
    config.version = _as_int(raw.get("version"), CONFIG_VERSION)
    if isinstance(raw.get("active_profile"), str):
        config.active_profile = raw["active_profile"]
    ui = raw.get("ui")
    if isinstance(ui, dict):
        config.ui = UiState(
            last_outdir=str(ui.get("last_outdir") or ""),
            show_system_dbs=bool(ui.get("show_system_dbs", False)),
        )
    profiles = [
        _profile_from_dict(item, warnings)
        for item in (raw.get("profiles") or [])
        if isinstance(item, dict)
    ]
    if profiles:
        config.profiles = profiles
    if config.version < CONFIG_VERSION:
        config.version = CONFIG_VERSION
        warnings.append("配置已升级到 v%d" % CONFIG_VERSION)
    ensure_active_profile(config)
    return config, warnings


def save_config(config: AppConfig, path: Path) -> None:
    """原子写入配置（先写 .tmp 再替换），密码 DPAPI 加密。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CONFIG_VERSION,
        "active_profile": config.active_profile,
        "ui": {
            "last_outdir": config.ui.last_outdir,
            "show_system_dbs": config.ui.show_system_dbs,
        },
        "profiles": [_profile_to_dict(item) for item in config.profiles],
    }
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
