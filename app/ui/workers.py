"""后台线程：测试连接、加载库/表、预览与执行导出，UI 不阻塞。"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.core.errors import translate_exception
from app.core.models import ExportOptions, Profile
from app.core.runner import ExportRunner
from app.dialects import create_dialect


class _DialectWorker(QThread):
    """带异常兜底的方言操作线程基类。"""

    sig_error = Signal(str, str)

    def __init__(self, profile: Profile, parent=None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.dialect = None

    def _connect(self):
        self.dialect = create_dialect(self.profile.dialect, self.profile)
        self.dialect.connect()
        return self.dialect

    def _close(self) -> None:
        """关闭连接；收尾阶段异常不外抛。"""
        if self.dialect is not None:
            try:
                self.dialect.close()
            except Exception:
                pass
            self.dialect = None

    def _emit_error(self, exc: BaseException) -> None:
        error = translate_exception(exc)
        self.sig_error.emit(error.message, error.detail)

    def run(self) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError


class PingWorker(_DialectWorker):
    sig_done = Signal(str)

    def run(self) -> None:
        try:
            self.sig_done.emit(self._connect().ping())
        except Exception as exc:
            self._emit_error(exc)
        finally:
            self._close()


class DatabasesWorker(_DialectWorker):
    sig_done = Signal(object)

    def __init__(self, profile: Profile, include_system: bool = False, parent=None) -> None:
        super().__init__(profile, parent)
        self.include_system = include_system

    def run(self) -> None:
        try:
            self.sig_done.emit(self._connect().list_databases(self.include_system))
        except Exception as exc:
            self._emit_error(exc)
        finally:
            self._close()


class TablesWorker(_DialectWorker):
    sig_done = Signal(object)

    def __init__(self, profile: Profile, db: str, parent=None) -> None:
        super().__init__(profile, parent)
        self.db = db

    def run(self) -> None:
        try:
            self.sig_done.emit(self._connect().list_tables(self.db))
        except Exception as exc:
            self._emit_error(exc)
        finally:
            self._close()


class PreviewWorker(_DialectWorker):
    sig_done = Signal(object)

    def __init__(self, profile: Profile, plans, options: ExportOptions, parent=None) -> None:
        super().__init__(profile, parent)
        self.plans = plans
        self.options = options

    def run(self) -> None:
        dialect = None
        try:
            dialect = create_dialect(self.profile.dialect, self.profile)
            runner = ExportRunner(dialect, self.options, Path("."))
            self.sig_done.emit(runner.preview(self.plans))
        except Exception as exc:
            self._emit_error(exc)
        finally:
            if dialect is not None:
                try:
                    dialect.close()
                except Exception:
                    pass


class RowCountWorker(_DialectWorker):
    """自动精确统计一个库所有表/视图的 COUNT(*)，逐表回报。"""

    sig_progress = Signal(str, str, int, int, int)  # db, table, rows, done, total
    sig_skipped = Signal(str, str, str)             # db, table, reason
    sig_done = Signal(str, object)                  # db, {table: rows}
    QUERY_TIMEOUT_MS = 10000

    def __init__(self, profile: Profile, db: str, tables, parent=None) -> None:
        super().__init__(profile, parent)
        self.db = db
        self.tables = list(tables)
        self.cancelled = False
        self._thread_id = None

    def cancel(self) -> None:
        """请求取消：不阻塞 UI，当前 COUNT 结束后退出（最多等查询超时）。"""
        self.cancelled = True

    def run(self) -> None:  # pragma: no cover - 需要真实数据库
        result = {}
        try:
            dialect = self._connect()
            connection = dialect._connection()
            with connection.cursor() as cursor:
                try:
                    cursor.execute("SET SESSION max_execution_time=%d" % self.QUERY_TIMEOUT_MS)
                except Exception:
                    pass
            total = len(self.tables)
            for index, name in enumerate(self.tables, 1):
                if self.cancelled:
                    break
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) FROM %s"
                                       % dialect.qualified(self.db, name))
                        row = cursor.fetchone()
                    result[name] = int(row[0]) if row else 0
                    self.sig_progress.emit(self.db, name, result[name], index, total)
                except Exception as exc:
                    if self.cancelled:
                        break
                    self.sig_skipped.emit(self.db, name, str(exc))
                    self.sig_progress.emit(self.db, name, -1, index, total)
        except Exception as exc:
            self._emit_error(exc)
        finally:
            self._close()
            self.sig_done.emit(self.db, result)


class ExportWorker(QThread):
    sig_log = Signal(str)
    sig_progress = Signal(object)
    sig_finished = Signal(object)
    sig_error = Signal(str, str)

    def __init__(self, profile: Profile, plans, options: ExportOptions, outdir,
                 parent=None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.plans = plans
        self.options = options
        self.outdir = Path(outdir)
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        dialect = None
        try:
            dialect = create_dialect(self.profile.dialect, self.profile)
            runner = ExportRunner(dialect, self.options, self.outdir,
                                  cancel_event=self.cancel_event,
                                  log=self.sig_log.emit)
            report = runner.export(self.plans, progress_cb=self.sig_progress.emit)
            self.sig_finished.emit(report)
        except Exception as exc:
            error = translate_exception(exc)
            self.sig_error.emit(error.message, error.detail)
        finally:
            if dialect is not None:
                try:
                    dialect.close()
                except Exception:
                    pass
