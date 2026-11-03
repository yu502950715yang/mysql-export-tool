"""内存方言：--selftest 与单元测试使用，不连接真实数据库。"""
from __future__ import annotations

from typing import Iterator

from app.core.models import KIND_TABLE, KIND_VIEW, ExportOptions, Profile, TableInfo

from .base import Dialect, DialectError, quote_ident


def default_schema() -> dict[str, dict[str, tuple[list[str], list[tuple]]]]:
    return {
        "db_a": {
            "users": (["id", "name"], [(1, "alice"), (2, "bob"), (3, "张三")]),
            "audit_log": (["id", "action"], [(1, "login")]),
        },
        "db_b": {"orders": (["id", "user_id"], [(10, 1), (11, 2)])},
        "selftest": {
            "users": (["id", "name"], [(1, "alice"), (2, "bob")]),
            "audit_log": (["id", "action"], [(1, "login")]),
        },
    }


def default_views() -> dict[str, dict[str, str]]:
    return {
        "db_a": {"v_users": "SELECT `id`, `name` FROM `users`"},
        "selftest": {"v_users": "SELECT `id`, `name` FROM `users`"},
    }


class MemoryDialect(Dialect):
    name = "memory"
    label = "Memory"

    def __init__(self, profile=None, *, schema=None, views=None, fail_databases=(),
                 fail_tables=(), fail_create_tables=(), fail_views=()) -> None:
        super().__init__(profile or Profile(name="memory"))
        self.schema = schema if schema is not None else default_schema()
        self.views = views if views is not None else default_views()
        self.fail_databases = set(fail_databases)
        self.fail_tables = set(fail_tables)
        self.fail_create_tables = set(fail_create_tables)
        self.fail_views = set(fail_views)
        self.connect_count = 0
        self.close_count = 0
        self._connected = False

    def connect(self) -> None:
        self._connected = True
        self.connect_count += 1

    def close(self) -> None:
        self._connected = False
        self.close_count += 1

    def _require_connection(self) -> None:
        if not self._connected:
            raise DialectError("尚未连接数据库")

    def ping(self) -> str:
        self._require_connection()
        return "8.0.0-memory"

    def list_databases(self, include_system: bool = False) -> list[str]:
        self._require_connection()
        return list(self.schema)

    def list_tables(self, db: str) -> list[TableInfo]:
        self._require_connection()
        if db in self.fail_databases:
            raise DialectError("模拟列表失败：%s" % db)
        result = [TableInfo(name, KIND_TABLE, len(rows))
                  for name, (_, rows) in sorted(self.schema.get(db, {}).items())]
        result += [TableInfo(name, KIND_VIEW, 0)
                   for name in sorted(self.views.get(db, {}))]
        return result

    def create_table_sql(self, db: str, table: str) -> str:
        self._require_connection()
        if table in self.fail_create_tables:
            raise DialectError("模拟建表读取失败：%s" % table)
        columns, _ = self.schema[db][table]
        column_sql = ",\n  ".join("%s varchar(255)" % quote_ident(name) for name in columns)
        return "CREATE TABLE %s (\n  %s\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" % (
            quote_ident(table), column_sql)

    def drop_table_sql(self, table: str) -> str:
        return "DROP TABLE IF EXISTS %s;" % quote_ident(table)

    def create_view_sql(self, db: str, view: str) -> str:
        self._require_connection()
        if view in self.fail_views:
            raise DialectError("模拟视图读取失败：%s" % view)
        definition = self.views[db][view]
        return "CREATE VIEW %s AS %s" % (quote_ident(view), definition)

    def drop_view_sql(self, view: str) -> str:
        return "DROP VIEW IF EXISTS %s;" % quote_ident(view)

    def stream_rows(self, db: str, table: str,
                    batch: int) -> Iterator[tuple[list[str], list[tuple]]]:
        self._require_connection()
        if table in self.fail_tables:
            raise DialectError("模拟读取失败：%s" % table)
        columns, rows = self.schema[db][table]
        for start in range(0, len(rows), batch):
            yield columns, rows[start:start + batch]

    def literal(self, value, options: ExportOptions) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, str):
            return "'%s'" % value.replace("'", "''")
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)
