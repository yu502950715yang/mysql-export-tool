"""数据模型：配置、导出计划、进度与报告。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

KIND_TABLE = "table"
KIND_VIEW = "view"

STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

DEFAULT_BATCH_SIZE = 1000


@dataclass
class ExcludeConfig:
    """一个库的排除配置：精确表名 + 正则。"""

    exclude_tables: list[str] = field(default_factory=list)
    exclude_regexes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exclude_tables": list(self.exclude_tables),
            "exclude_regexes": list(self.exclude_regexes),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "ExcludeConfig":
        raw = raw if isinstance(raw, dict) else {}
        tables = raw.get("exclude_tables")
        regexes = raw.get("exclude_regexes")
        return cls(
            exclude_tables=[str(x) for x in tables] if isinstance(tables, list) else [],
            exclude_regexes=[str(x) for x in regexes] if isinstance(regexes, list) else [],
        )


@dataclass
class ExportOptions:
    """导出选项，随 profile 持久化。"""

    escape_unicode: bool = True
    drop_before_create: bool = True
    include_views: bool = True
    batch_size: int = DEFAULT_BATCH_SIZE
    filename_timestamp: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "escape_unicode": self.escape_unicode,
            "drop_before_create": self.drop_before_create,
            "include_views": self.include_views,
            "batch_size": self.batch_size,
            "filename_timestamp": self.filename_timestamp,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "ExportOptions":
        raw = raw if isinstance(raw, dict) else {}
        options = cls()
        for name in ("escape_unicode", "drop_before_create", "include_views",
                     "filename_timestamp"):
            if isinstance(raw.get(name), bool):
                setattr(options, name, raw[name])
        batch = raw.get("batch_size")
        if isinstance(batch, int) and not isinstance(batch, bool) and 1 <= batch <= 100000:
            options.batch_size = batch
        return options


@dataclass
class Profile:
    """一套数据库连接配置。密码仅存内存明文，落盘走 DPAPI。"""

    name: str = "default"
    dialect: str = "mysql"
    host: str = ""
    port: int = 3306
    user: str = ""
    password: str = ""
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    databases: dict[str, ExcludeConfig] = field(default_factory=dict)
    selected_databases: list[str] = field(default_factory=list)
    options: ExportOptions = field(default_factory=ExportOptions)

    def exclude_for(self, db: str) -> ExcludeConfig:
        """返回该库的排除配置；未配置过的库返回空配置。"""
        cfg = self.databases.get(db)
        return cfg if cfg is not None else ExcludeConfig()


@dataclass
class UiState:
    last_outdir: str = ""
    show_system_dbs: bool = False


@dataclass
class AppConfig:
    version: int = 1
    active_profile: str = "default"
    ui: UiState = field(default_factory=UiState)
    profiles: list[Profile] = field(default_factory=list)

    def profile(self, name: str | None = None) -> Profile | None:
        """按名字取 profile；name 为空取 active_profile。"""
        wanted = name or self.active_profile
        for item in self.profiles:
            if item.name == wanted:
                return item
        return None


@dataclass
class TableInfo:
    name: str
    kind: str = KIND_TABLE
    est_rows: int = 0
    comment: str = ""
    rows_exact: bool = False
    rows_note: str = ""

    @property
    def is_view(self) -> bool:
        return self.kind == KIND_VIEW


@dataclass
class ClassifiedTable:
    info: TableInfo
    export_data: bool
    export_structure: bool
    reason: str = ""


@dataclass
class DatabasePlan:
    db: str
    exclude: ExcludeConfig = field(default_factory=ExcludeConfig)


@dataclass
class TableResult:
    name: str
    kind: str
    rows: int = 0
    error: str = ""


@dataclass
class DatabaseResult:
    db: str
    path: str = ""
    tables: list[TableResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class ExportReport:
    status: str = STATUS_SUCCESS
    started_at: datetime | None = None
    elapsed: float = 0.0
    databases: list[DatabaseResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_tables(self) -> int:
        return sum(len(item.tables) for item in self.databases)

    @property
    def total_rows(self) -> int:
        return sum(t.rows for item in self.databases for t in item.tables)


@dataclass
class ProgressInfo:
    db: str = ""
    db_index: int = 0
    db_total: int = 0
    table: str = ""
    rows_in_table: int = 0
    tables_done: int = 0
    tables_total: int = 0
    elapsed: float = 0.0


@dataclass
class PreviewDatabase:
    db: str
    classified: list[ClassifiedTable] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PreviewReport:
    databases: list[PreviewDatabase] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
