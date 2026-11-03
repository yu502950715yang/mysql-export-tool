"""命令行入口：--version / --selftest / --dry-run。"""
from __future__ import annotations

import argparse

from app import APP_NAME, APP_TITLE, __version__
from app.core import config as config_mod
from app.core.models import DatabasePlan, ExcludeConfig
from app.core.runner import ExportRunner
from app.dialects import create_dialect
from app.selftest import run_selftest_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_TITLE)
    parser.add_argument("--version", action="store_true", help="打印版本号")
    parser.add_argument("--selftest", action="store_true", help="运行内置自检（不启动界面）")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--profile", help="使用的配置名")
    parser.add_argument("--dry-run", action="store_true", help="预览导出清单，不写文件")
    parser.add_argument("--outdir", help="输出目录（预留参数）")
    parser.add_argument("--databases", help="逗号分隔的库名（覆盖配置中勾选的库）")
    parser.add_argument("--exclude-tables", help="逗号分隔的追加排除表")
    parser.add_argument("--exclude-regex", action="append", default=[],
                        help="追加排除正则，可重复")
    return parser


def _run_dry_run(args) -> int:
    path = config_mod.default_config_path(args.config)
    app_config, warnings = config_mod.load_config(path)
    for warning in warnings:
        print("提示：" + warning)
    profile = app_config.profile(args.profile)
    if profile is None:
        print("没有可用配置，请先在 GUI 中创建")
        return 2
    if not profile.host or not profile.user:
        print("配置不完整：缺少 host 或 user，请先在 GUI 中填写")
        return 2
    if args.databases:
        databases = [name.strip() for name in args.databases.split(",") if name.strip()]
    else:
        databases = list(profile.selected_databases)
    if not databases:
        print("未指定要导出的库：请用 --databases 指定，或先在 GUI 中勾选")
        return 2
    extra_tables = [name.strip() for name in (args.exclude_tables or "").split(",")
                    if name.strip()]
    extra_regexes = [pattern for pattern in args.exclude_regex if pattern.strip()]
    plans = []
    for db in databases:
        base = profile.exclude_for(db)
        plans.append(DatabasePlan(db, ExcludeConfig(
            exclude_tables=list(base.exclude_tables) + extra_tables,
            exclude_regexes=list(base.exclude_regexes) + extra_regexes)))
    dialect = create_dialect(profile.dialect, profile)
    runner = ExportRunner(dialect, profile.options, config_mod.default_export_dir(),
                          log=print)
    report = runner.preview(plans)
    exit_code = 0
    for item in report.databases:
        if item.errors:
            exit_code = 1
            print("数据库 %s 失败：%s" % (item.db, "；".join(item.errors)))
            continue
        data_tables = [c for c in item.classified
                       if not c.info.is_view and c.export_data]
        structure_only = [c for c in item.classified
                          if not c.info.is_view and not c.export_data]
        views = [c for c in item.classified if c.info.is_view and c.export_structure]
        est_rows = sum(c.info.est_rows for c in data_tables)
        print("数据库 %s：导出表 %d，仅结构 %d，视图 %d，估算行数 %s"
              % (item.db, len(data_tables), len(structure_only), len(views),
                 format(est_rows, ",")))
        for classified in structure_only:
            print("  仅结构：%s（%s）" % (classified.info.name, classified.reason))
    print("（dry-run：未写任何文件）")
    return exit_code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print("%s v%s" % (APP_NAME, __version__))
        return 0
    if args.selftest:
        return run_selftest_cli()
    if args.dry_run:
        return _run_dry_run(args)
    print("未选择操作：GUI 模式请直接双击运行；命令行支持 --selftest / --dry-run / --version")
    return 2
