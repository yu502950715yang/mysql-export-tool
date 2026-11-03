"""导出编排：逐库连接、分类、写出，汇总进度/取消/报告。"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .classify import classify_tables
from .errors import translate_exception
from .models import (DatabasePlan, DatabaseResult, ExportOptions, ExportReport,
                     PreviewDatabase, PreviewReport, ProgressInfo,
                     STATUS_CANCELLED, STATUS_FAILED, STATUS_PARTIAL, STATUS_SUCCESS)
from .writer_sql import SqlWriter

if TYPE_CHECKING:
    from ..dialects.base import Dialect

ProgressCallback = Callable[[ProgressInfo], None]
LogCallback = Callable[[str], None]


def output_path_for(outdir: Path, db: str, options: ExportOptions) -> Path:
    """按库生成输出文件路径（可选时间戳后缀）。"""
    filename = db
    if options.filename_timestamp:
        filename += "_" + time.strftime("%Y%m%d_%H%M%S")
    return Path(outdir) / ("%s.sql" % filename)


class ExportRunner:
    """把「导出计划」变成若干 .sql 文件。"""

    def __init__(self, dialect: "Dialect", options: ExportOptions, outdir,
                 cancel_event=None, log: LogCallback | None = None) -> None:
        self.dialect = dialect
        self.options = options
        self.outdir = Path(outdir)
        self.cancel_event = cancel_event
        self.log = log or (lambda message: None)
        self._started = 0.0

    def preview(self, plans: list[DatabasePlan]) -> PreviewReport:
        """只做库表发现与分类统计，不写文件。"""
        report = PreviewReport()
        for plan in plans:
            item = PreviewDatabase(db=plan.db)
            try:
                self.dialect.connect()
                tables = self.dialect.list_tables(plan.db)
                item.classified = classify_tables(tables, plan.exclude,
                                                  self.options.include_views)
            except Exception as exc:
                message = translate_exception(exc).message
                item.errors.append(message)
                report.errors.append("%s：%s" % (plan.db, message))
            finally:
                self.dialect.close()
            report.databases.append(item)
        return report

    def export(self, plans: list[DatabasePlan],
               progress_cb: ProgressCallback | None = None) -> ExportReport:
        self._started = time.time()
        report = ExportReport(started_at=datetime.now())
        try:
            self.outdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            report.status = STATUS_FAILED
            report.errors.append("输出目录不可用：%s" % exc)
            return report
        db_total = len(plans)
        for index, plan in enumerate(plans):
            if self._cancelled():
                report.status = STATUS_CANCELLED
                break
            self.log("===== 数据库 %s =====" % plan.db)
            db_result = self._export_one(plan, index, db_total, progress_cb)
            report.databases.append(db_result)
            report.errors.extend(db_result.errors)
            if db_result.cancelled:
                report.status = STATUS_CANCELLED
                break
            if db_result.errors:
                report.status = STATUS_PARTIAL
        if (report.status == STATUS_SUCCESS and report.databases
                and all(item.errors for item in report.databases)):
            report.status = STATUS_FAILED
        report.elapsed = time.time() - self._started
        return report

    def _export_one(self, plan: DatabasePlan, index: int, db_total: int,
                    progress_cb: ProgressCallback | None) -> DatabaseResult:
        try:
            self.dialect.connect()
            tables = self.dialect.list_tables(plan.db)
            classified = classify_tables(tables, plan.exclude, self.options.include_views)
            path = output_path_for(self.outdir, plan.db, self.options)
            writer = SqlWriter(self.dialect, self.options, self.cancel_event, self.log)
            callback = None
            if progress_cb is not None:
                total_tables = len(classified)

                def callback(table, rows_in_table, tables_done, _db=plan.db, _index=index,
                             _db_total=db_total, _total_tables=total_tables):
                    progress_cb(ProgressInfo(
                        db=_db, db_index=_index, db_total=_db_total, table=table,
                        rows_in_table=rows_in_table, tables_done=tables_done,
                        tables_total=_total_tables, elapsed=time.time() - self._started))
            result = writer.write_database(plan.db, classified, path, callback)
            self.log("  -> 已生成：%s" % result.path)
            return result
        except Exception as exc:
            app_error = translate_exception(exc)
            message = "数据库 %s 导出失败：%s" % (plan.db, app_error.message)
            self.log(message)
            if app_error.detail:
                self.log("  详情：%s" % app_error.detail)
            return DatabaseResult(db=plan.db, errors=[message])
        finally:
            self.dialect.close()

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()
