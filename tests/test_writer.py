import threading

import pytest

from app.core.classify import classify_tables
from app.core.models import ExcludeConfig, ExportOptions
from app.core.writer_sql import SqlWriter
from app.dialects.memory import MemoryDialect


@pytest.fixture()
def writer_ctx(tmp_path):
    dialect = MemoryDialect()
    dialect.connect()
    tables = dialect.list_tables("db_a")
    classified = classify_tables(tables, ExcludeConfig(exclude_regexes=[r".*_log$"]))

    def build(options=None, cancel_event=None, items=None):
        options = options or ExportOptions()
        writer = SqlWriter(dialect, options, cancel_event, log=lambda message: None)
        path = tmp_path / "db_a.sql"
        result = writer.write_database("db_a", items if items is not None else classified,
                                       path)
        return result, path.read_text(encoding="utf-8")

    yield build
    dialect.close()


def test_excluded_table_has_create_but_no_insert(writer_ctx):
    result, text = writer_ctx()
    assert result.errors == []
    assert "CREATE TABLE `audit_log`" in text
    assert "INSERT INTO `audit_log`" not in text
    assert "excluded tables (structure only): audit_log" in text


def test_exported_table_has_data_and_row_comment(writer_ctx):
    result, text = writer_ctx()
    assert "INSERT INTO `users` (`id`,`name`) VALUES (1,'alice');" in text
    assert "-- table `users` rows: 3" in text
    users = {item.name: item for item in result.tables}["users"]
    assert users.rows == 3


def test_view_after_all_tables(writer_ctx):
    _, text = writer_ctx()
    assert text.index("CREATE VIEW `v_users`") > text.index("CREATE TABLE `users`")


def test_footer_present(writer_ctx):
    _, text = writer_ctx()
    assert text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")
    assert text.index("SET FOREIGN_KEY_CHECKS=0;") < text.index("CREATE TABLE `audit_log`")


def test_drop_can_be_disabled(writer_ctx):
    _, text = writer_ctx(options=ExportOptions(drop_before_create=False))
    assert "DROP TABLE" not in text
    assert "DROP VIEW" not in text


def test_views_can_be_disabled():
    dialect = MemoryDialect()
    dialect.connect()
    classified = classify_tables(dialect.list_tables("db_a"), ExcludeConfig(),
                                 include_views=False)
    writer = SqlWriter(dialect, ExportOptions(), None)
    import pathlib
    import tempfile

    path = pathlib.Path(tempfile.mkdtemp()) / "db_a.sql"
    writer.write_database("db_a", classified, path)
    text = path.read_text(encoding="utf-8")
    assert "CREATE VIEW" not in text
    dialect.close()


def test_read_failure_recorded_and_structure_kept(tmp_path):
    dialect = MemoryDialect(fail_tables={"users"})
    dialect.connect()
    classified = classify_tables(dialect.list_tables("db_a"),
                                 ExcludeConfig(exclude_regexes=[r".*_log$"]))
    writer = SqlWriter(dialect, ExportOptions(), None)
    path = tmp_path / "db_a.sql"
    result = writer.write_database("db_a", classified, path)
    text = path.read_text(encoding="utf-8")
    assert result.errors, "读表失败应记录错误"
    assert "CREATE TABLE `users`" in text
    assert "INSERT INTO `users`" not in text
    assert text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")
    dialect.close()


def test_cancel_before_first_table(tmp_path):
    dialect = MemoryDialect()
    dialect.connect()
    classified = classify_tables(dialect.list_tables("db_a"), ExcludeConfig())
    cancel = threading.Event()
    cancel.set()
    writer = SqlWriter(dialect, ExportOptions(), cancel)
    path = tmp_path / "db_a.sql"
    result = writer.write_database("db_a", classified, path)
    text = path.read_text(encoding="utf-8")
    assert result.cancelled is True
    assert text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")
    dialect.close()
