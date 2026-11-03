"""--selftest：用内存方言跑一遍导出并校验产物，供打包冒烟。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from app import APP_TITLE, __version__
from app.core.config import exe_dir
from app.core.models import DatabasePlan, ExcludeConfig, ExportOptions
from app.core.runner import ExportRunner
from app.dialects.memory import MemoryDialect

SELFTEST_LOG_NAME = "selftest.log"


def selftest_log_path() -> Path:
    """自检日志优先写 exe 同目录，失败回退临时目录。"""
    candidate = exe_dir() / SELFTEST_LOG_NAME
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("", encoding="utf-8")
        return candidate
    except OSError:
        return Path(tempfile.gettempdir()) / ("MysqlExportTool-" + SELFTEST_LOG_NAME)


def run_selftest() -> tuple[bool, list[str]]:
    """内存方言导出 + 产物断言，返回 (是否通过, 输出行)。"""
    lines = ["%s v%s 自检" % (APP_TITLE, __version__)]
    with tempfile.TemporaryDirectory(prefix="mysql-export-selftest-") as tmp:
        outdir = Path(tmp)
        runner = ExportRunner(MemoryDialect(), ExportOptions(), outdir, log=lines.append)
        plan = [DatabasePlan("selftest", ExcludeConfig(exclude_tables=["audit_log"]))]
        report = runner.export(plan)
        sql_path = Path(report.databases[0].path) if report.databases else None
        text = sql_path.read_text(encoding="utf-8") if sql_path and sql_path.exists() else ""
        checks = [
            ("导出报告成功", report.status == "success"),
            ("生成 SQL 文件", sql_path is not None and sql_path.exists()),
            ("导出表有数据", "INSERT INTO `users`" in text),
            ("排除表无数据", "INSERT INTO `audit_log`" not in text),
            ("排除表保留建表", "CREATE TABLE `audit_log`" in text),
            ("视图已导出", "CREATE VIEW `v_users`" in text),
            ("文件尾部语句正确", text.rstrip().endswith("SET FOREIGN_KEY_CHECKS=1;")),
            ("排除表清单写入文件头", "excluded tables (structure only): audit_log" in text),
        ]
    ok = True
    for name, passed in checks:
        ok = ok and passed
        lines.append(("PASS " if passed else "FAIL ") + name)
    lines.append("SELFTEST OK" if ok else "SELFTEST FAILED")
    return ok, lines


def run_selftest_cli() -> int:
    """命令行自检：写 selftest.log 并返回退出码。"""
    ok, lines = run_selftest()
    path = selftest_log_path()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("自检日志：%s" % path)
    return 0 if ok else 1
