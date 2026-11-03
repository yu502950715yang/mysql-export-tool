from app.core.models import (AppConfig, ClassifiedTable, DatabaseResult, ExcludeConfig,
                             ExportOptions, ExportReport, Profile, TableInfo, TableResult)


def test_exclude_config_roundtrip():
    cfg = ExcludeConfig(exclude_tables=["sys_oper_log"], exclude_regexes=[".*_log$"])
    assert cfg.to_dict() == {"exclude_tables": ["sys_oper_log"], "exclude_regexes": [".*_log$"]}
    assert ExcludeConfig.from_dict(cfg.to_dict()) == cfg


def test_exclude_config_from_bad_input_falls_back_to_empty():
    assert ExcludeConfig.from_dict({"exclude_tables": "oops", "exclude_regexes": None}) == ExcludeConfig()


def test_export_options_defaults_and_roundtrip():
    options = ExportOptions()
    assert options.escape_unicode is True
    assert options.batch_size == 1000
    assert ExportOptions.from_dict(options.to_dict()) == options


def test_profile_exclude_for_missing_db_returns_empty():
    profile = Profile(name="dev")
    assert profile.exclude_for("db1") == ExcludeConfig()


def test_table_info_view_flag():
    assert TableInfo("v1", "view").is_view is True
    assert TableInfo("t1", "table").is_view is False


def test_classified_table_fields():
    item = ClassifiedTable(TableInfo("t1"), export_data=False, export_structure=True,
                           reason="未勾选")
    assert (item.export_data, item.export_structure, item.reason) == (False, True, "未勾选")


def test_report_totals():
    report = ExportReport(databases=[
        DatabaseResult(db="a", tables=[TableResult("t1", "table", 3),
                                       TableResult("v1", "view", 0)]),
        DatabaseResult(db="b", tables=[TableResult("t2", "table", 2)]),
    ])
    assert report.total_tables == 3
    assert report.total_rows == 5


def test_app_config_profile_lookup():
    config = AppConfig(active_profile="b", profiles=[Profile(name="a"), Profile(name="b")])
    assert config.profile().name == "b"
    assert config.profile("a").name == "a"
    assert config.profile("missing") is None
