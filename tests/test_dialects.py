import pytest

from app.core.literal import quote_ident
from app.core.models import ExportOptions, Profile
from app.dialects import DIALECTS, create_dialect, dialect_label
from app.dialects.base import DialectError
from app.dialects.memory import MemoryDialect
from app.dialects.mysql import MySQLDialect


def test_quote_ident_escapes_backtick():
    assert quote_ident("users") == "`users`"
    assert quote_ident("we`ird") == "`we``ird`"


def test_registry_known_dialect():
    assert set(DIALECTS) == {"mysql", "memory"}
    assert dialect_label("mysql") == "MySQL"
    dialect = create_dialect("mysql", Profile(name="p"))
    assert isinstance(dialect, MySQLDialect)
    assert dialect.name == "mysql"


def test_registry_unknown_dialect_raises():
    with pytest.raises(DialectError):
        create_dialect("postgres", Profile(name="p"))


def test_mysql_qualified_name():
    assert MySQLDialect.qualified("db1", "t1") == "`db1`.`t1`"


def test_memory_listing_order_and_kinds():
    dialect = MemoryDialect()
    dialect.connect()
    assert dialect.list_databases() == ["db_a", "db_b", "selftest"]
    tables = dialect.list_tables("db_a")
    assert [item.name for item in tables] == ["audit_log", "users", "v_users"]
    kinds = {item.name: item.kind for item in tables}
    assert kinds["v_users"] == "view"
    assert kinds["users"] == "table"
    assert {item.name: item.est_rows for item in tables}["users"] == 3


def test_memory_stream_rows_batches():
    dialect = MemoryDialect()
    dialect.connect()
    batches = list(dialect.stream_rows("db_a", "users", batch=2))
    assert [len(rows) for _, rows in batches] == [2, 1]
    assert batches[0][0] == ["id", "name"]


def test_memory_literal_simple_rules():
    dialect = MemoryDialect()
    dialect.connect()
    options = ExportOptions()
    assert dialect.literal(None, options) == "NULL"
    assert dialect.literal("O'Brien", options) == "'O''Brien'"
    assert dialect.literal(7, options) == "7"


def test_memory_failure_injection():
    dialect = MemoryDialect(fail_databases={"db_b"}, fail_tables={"users"},
                            fail_views={"v_users"})
    dialect.connect()
    with pytest.raises(DialectError):
        dialect.list_tables("db_b")
    with pytest.raises(DialectError):
        next(iter(dialect.stream_rows("db_a", "users", 10)))
    with pytest.raises(DialectError):
        dialect.create_view_sql("db_a", "v_users")


def test_memory_requires_connection():
    dialect = MemoryDialect()
    with pytest.raises(DialectError):
        dialect.list_tables("db_a")


class _FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.connection.statements.append(sql)
        if sql.startswith("SHOW FULL TABLES"):
            self.result = [("users", "BASE TABLE"), ("v_users", "VIEW")]
        elif sql.startswith("SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT"):
            if self.connection.fail_estimates:
                raise RuntimeError("模拟统计查询超时")
            self.result = [("users", 7, "用户表")]
        else:
            self.result = []

    def fetchall(self):
        return list(self.result)


class _FakeConnection:
    def __init__(self, fail_estimates=False):
        self.statements = []
        self.fail_estimates = fail_estimates

    def cursor(self):
        return _FakeCursor(self)


def _dialect_with(connection):
    dialect = MySQLDialect(Profile(name="p"))
    dialect._conn = connection
    return dialect


def test_mysql_list_tables_show_full_tables_and_estimates():
    fake = _FakeConnection()
    tables = _dialect_with(fake).list_tables("db1")
    assert [item.name for item in tables] == ["users", "v_users"]
    assert [item.kind for item in tables] == ["table", "view"]
    assert tables[0].est_rows == 7
    assert tables[0].comment == "用户表"
    assert any(sql.startswith("SHOW FULL TABLES") for sql in fake.statements)


def test_mysql_list_tables_estimate_failure_is_non_blocking():
    fake = _FakeConnection(fail_estimates=True)
    tables = _dialect_with(fake).list_tables("db1")
    assert [item.name for item in tables] == ["users", "v_users"]
    assert all(item.est_rows == 0 and item.comment == "" for item in tables)
    assert "SET SESSION max_execution_time=0" in fake.statements
