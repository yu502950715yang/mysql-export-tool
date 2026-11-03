import threading
from pathlib import Path

from app.core.models import (DatabasePlan, ExcludeConfig, ExportOptions,
                             STATUS_CANCELLED, STATUS_FAILED, STATUS_PARTIAL,
                             STATUS_SUCCESS)
from app.core.runner import ExportRunner, output_path_for
from app.dialects.memory import MemoryDialect


def _runner(tmp_path, **kwargs):
    return ExportRunner(MemoryDialect(**kwargs), ExportOptions(batch_size=2), tmp_path,
                        log=lambda message: None)


def test_export_two_databases(tmp_path):
    runner = _runner(tmp_path)
    plans = [DatabasePlan("db_a", ExcludeConfig(exclude_regexes=[".*_log$"])),
             DatabasePlan("db_b")]
    report = runner.export(plans)
    assert report.status == STATUS_SUCCESS
    assert report.total_rows == 5
    text = (tmp_path / "db_a.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE `audit_log`" in text
    assert "INSERT INTO `audit_log`" not in text
    assert report.elapsed >= 0


def test_cancel_on_progress(tmp_path):
    cancel = threading.Event()
    runner = _runner(tmp_path)
    runner.cancel_event = cancel

    def on_progress(info):
        if info.table == "users" and info.rows_in_table >= 2:
            cancel.set()

    report = runner.export(
        [DatabasePlan("db_a", ExcludeConfig(exclude_regexes=[".*_log$"]))],
        progress_cb=on_progress)
    assert report.status == STATUS_CANCELLED
    text = (tmp_path / "db_a.sql").read_text(encoding="utf-8")
    assert text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")


def test_single_database_failure_is_partial(tmp_path):
    runner = _runner(tmp_path, fail_databases={"db_b"})
    report = runner.export([DatabasePlan("db_a"), DatabasePlan("db_b")])
    assert report.status == STATUS_PARTIAL
    assert any("db_b" in message for message in report.errors)
    assert (tmp_path / "db_a.sql").exists()


def test_table_failure_keeps_file_importable(tmp_path):
    runner = _runner(tmp_path, fail_tables={"users"})
    report = runner.export([DatabasePlan("db_a",
                                         ExcludeConfig(exclude_regexes=[".*_log$"]))])
    assert report.status == STATUS_PARTIAL
    text = (tmp_path / "db_a.sql").read_text(encoding="utf-8")
    assert "INSERT INTO `users`" not in text
    assert "CREATE TABLE `users`" in text
    assert text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")


def test_preview_does_not_write_files(tmp_path):
    runner = _runner(tmp_path)
    report = runner.preview([DatabasePlan("db_a",
                                          ExcludeConfig(exclude_regexes=[".*_log$"]))])
    assert not list(Path(tmp_path).glob("*.sql"))
    item = report.databases[0]
    by_name = {c.info.name: c for c in item.classified}
    assert by_name["audit_log"].export_data is False
    assert by_name["audit_log"].export_structure is True
    assert by_name["users"].export_data is True
    assert by_name["v_users"].export_structure is True


def test_outdir_is_file_returns_failed(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    runner = ExportRunner(MemoryDialect(), ExportOptions(), blocker,
                          log=lambda message: None)
    report = runner.export([DatabasePlan("db_a")])
    assert report.status == STATUS_FAILED


def test_output_path_for_timestamp():
    options = ExportOptions(filename_timestamp=True)
    path = output_path_for(Path("out"), "db1", options)
    assert path.parent == Path("out")
    assert path.name.startswith("db1_")
    assert path.suffix == ".sql"
