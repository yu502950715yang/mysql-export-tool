import pytest

pytest.importorskip("PySide6")

from app.core.models import (DatabasePlan, ExcludeConfig, ExportOptions, Profile,
                             STATUS_SUCCESS)
from app.dialects.memory import MemoryDialect
from app.ui import workers


def _wait(worker, qapp, timeout_ms=15000):
    worker.start()
    assert worker.wait(timeout_ms), "后台线程未在超时内结束"
    qapp.processEvents()


@pytest.fixture(autouse=True)
def fake_dialect(monkeypatch):
    monkeypatch.setattr(workers, "create_dialect",
                        lambda name, profile: MemoryDialect())


def test_ping_worker(qapp):
    got = []
    worker = workers.PingWorker(Profile(name="p"))
    worker.sig_done.connect(got.append)
    _wait(worker, qapp)
    assert got == ["8.0.0-memory"]


def test_databases_worker(qapp):
    got = []
    worker = workers.DatabasesWorker(Profile(name="p"))
    worker.sig_done.connect(got.append)
    _wait(worker, qapp)
    assert got == [["db_a", "db_b", "selftest"]]


def test_tables_worker(qapp):
    got = []
    worker = workers.TablesWorker(Profile(name="p"), "db_a")
    worker.sig_done.connect(got.append)
    _wait(worker, qapp)
    assert [item.name for item in got[0]] == ["audit_log", "users", "v_users"]


def test_preview_worker(qapp):
    got = []
    plans = [DatabasePlan("db_a", ExcludeConfig(exclude_regexes=[".*_log$"]))]
    worker = workers.PreviewWorker(Profile(name="p"), plans, ExportOptions())
    worker.sig_done.connect(got.append)
    _wait(worker, qapp)
    assert got[0].databases[0].db == "db_a"


def test_export_worker(qapp, tmp_path):
    reports = []
    logs = []
    plans = [DatabasePlan("db_a", ExcludeConfig(exclude_regexes=[".*_log$"]))]
    worker = workers.ExportWorker(Profile(name="p"), plans, ExportOptions(), tmp_path)
    worker.sig_finished.connect(reports.append)
    worker.sig_log.connect(logs.append)
    _wait(worker, qapp)
    assert reports and reports[0].status == STATUS_SUCCESS
    assert (tmp_path / "db_a.sql").exists()
    assert logs


def test_export_worker_reports_errors_as_signal(qapp, monkeypatch, tmp_path):
    def boom_factory(name, profile):
        raise RuntimeError("boom")

    monkeypatch.setattr(workers, "create_dialect", boom_factory)
    errors = []
    worker = workers.ExportWorker(Profile(name="p"), [DatabasePlan("db_a")],
                                  ExportOptions(), tmp_path)
    worker.sig_error.connect(lambda message, detail: errors.append((message, detail)))
    _wait(worker, qapp)
    assert errors and "数据库操作失败" in errors[0][0]
