"""MySQL/MariaDB 方言实现（PyMySQL）。"""
from __future__ import annotations

from typing import Iterator

import pymysql
from pymysql.cursors import SSCursor

from app.core.literal import quote_ident, sql_literal
from app.core.models import KIND_TABLE, KIND_VIEW, ExportOptions, TableInfo

from .base import Dialect, DialectError

SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


class MySQLDialect(Dialect):
    name = "mysql"
    label = "MySQL"

    def __init__(self, profile) -> None:
        super().__init__(profile)
        self._conn = None

    @staticmethod
    def qualified(db: str, table: str) -> str:
        return "%s.%s" % (quote_ident(db), quote_ident(table))

    def connect(self) -> None:
        self._conn = pymysql.connect(
            host=self.profile.host,
            port=self.profile.port,
            user=self.profile.user,
            password=self.profile.password,
            charset=self.profile.charset or "utf8mb4",
            connect_timeout=self.profile.connect_timeout or 10,
            autocommit=True,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _connection(self):
        if self._conn is None:
            raise DialectError("尚未连接数据库")
        return self._conn

    def ping(self) -> str:
        with self._connection().cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
        return str(row[0]) if row else "unknown"

    def list_databases(self, include_system: bool = False) -> list[str]:
        with self._connection().cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            names = [str(row[0]) for row in cursor.fetchall()]
        if include_system:
            return names
        return [name for name in names if name.lower() not in SYSTEM_DATABASES]

    def list_tables(self, db: str) -> list[TableInfo]:
        """先用 SHOW FULL TABLES 快速拿到表/视图，行数估算带超时、失败不阻塞。

        information_schema.TABLES 在部分库上会因元数据/统计冷缓存卡 5–15 秒，
        UI 不能等它；估算行数只是展示信息，拿不到就按 0 处理。
        """
        with self._connection().cursor() as cursor:
            cursor.execute("SHOW FULL TABLES FROM %s" % quote_ident(db))
            rows = cursor.fetchall()
        tables = []
        for row in rows:
            name = str(row[0])
            table_type = str(row[1]).upper() if len(row) > 1 else ""
            kind = KIND_VIEW if table_type == "VIEW" else KIND_TABLE
            tables.append(TableInfo(name, kind, 0))
        stats = self._load_table_stats(db)
        for table in tables:
            table.est_rows, table.comment = stats.get(table.name, (0, ""))
        tables.sort(key=lambda item: (item.is_view, item.name))
        return tables

    def _load_table_stats(self, db: str) -> dict[str, tuple[int, str]]:
        """尽力读取行数估算与表注释；超过 1.5 秒就放弃，保证列表秒开。"""
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                try:
                    cursor.execute("SET SESSION max_execution_time=1500")
                except Exception:
                    pass  # MariaDB 等不支持时跳过，仅失去超时保护
                cursor.execute(
                    "SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT "
                    "FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s", (db,))
                rows = cursor.fetchall()
        except Exception:
            return {}
        finally:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET SESSION max_execution_time=0")
            except Exception:
                pass
        stats: dict[str, tuple[int, str]] = {}
        for name, table_rows, comment in rows:
            text = str(comment or "")
            stats[str(name)] = (int(table_rows or 0),
                                "" if text.upper() == "VIEW" else text)
        return stats

    def create_table_sql(self, db: str, table: str) -> str:
        with self._connection().cursor() as cursor:
            cursor.execute("SHOW CREATE TABLE %s" % self.qualified(db, table))
            row = cursor.fetchone()
        if not row or len(row) < 2:
            raise DialectError("无法读取建表语句：%s" % table)
        return str(row[1])

    def drop_table_sql(self, table: str) -> str:
        return "DROP TABLE IF EXISTS %s;" % quote_ident(table)

    def create_view_sql(self, db: str, view: str) -> str:
        sql = ("SELECT VIEW_DEFINITION FROM information_schema.VIEWS "
               "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s")
        with self._connection().cursor() as cursor:
            cursor.execute(sql, (db, view))
            row = cursor.fetchone()
        if not row or not row[0]:
            raise DialectError("无法读取视图定义（可能权限不足）：%s" % view)
        definition = str(row[0]).strip().rstrip(";")
        return "CREATE VIEW %s AS %s" % (quote_ident(view), definition)

    def drop_view_sql(self, view: str) -> str:
        return "DROP VIEW IF EXISTS %s;" % quote_ident(view)

    def stream_rows(self, db: str, table: str,
                    batch: int) -> Iterator[tuple[list[str], list[tuple]]]:
        cursor = self._connection().cursor(SSCursor)
        try:
            cursor.execute("SELECT * FROM %s" % self.qualified(db, table))
            columns = [item[0] for item in cursor.description]
            while True:
                rows = cursor.fetchmany(batch)
                if not rows:
                    break
                yield columns, rows
        finally:
            cursor.close()

    def literal(self, value, options: ExportOptions) -> str:
        return sql_literal(self._connection(), value, options.escape_unicode)
