import pytest

from app.core.classify import (RegexError, classify_tables, compile_regexes,
                               validate_regexes)
from app.core.models import ExcludeConfig, KIND_VIEW, TableInfo


def _tables():
    return [TableInfo("users", "table", 3), TableInfo("sys_oper_log", "table", 100),
            TableInfo("v_users", KIND_VIEW)]


def test_unchecked_table_is_structure_only():
    result = classify_tables(_tables(), ExcludeConfig(exclude_tables=["Users"]))
    by_name = {item.info.name: item for item in result}
    assert by_name["users"].export_data is False
    assert by_name["users"].export_structure is True
    assert "未勾选" in by_name["users"].reason
    assert by_name["sys_oper_log"].export_data is True


def test_regex_excludes_case_insensitively():
    result = classify_tables(_tables(), ExcludeConfig(exclude_regexes=[r".*_log$"]))
    by_name = {item.info.name: item for item in result}
    assert by_name["sys_oper_log"].export_data is False
    assert by_name["sys_oper_log"].export_structure is True
    assert "命中正则" in by_name["sys_oper_log"].reason


def test_regex_takes_precedence_over_unchecked():
    exclude = ExcludeConfig(exclude_tables=["sys_oper_log"], exclude_regexes=[r".*_log$"])
    result = classify_tables(_tables(), exclude)
    item = {i.info.name: i for i in result}["sys_oper_log"]
    assert "命中正则" in item.reason


def test_views_can_be_disabled():
    result = classify_tables(_tables(), ExcludeConfig(), include_views=False)
    view = {item.info.name: item for item in result}["v_users"]
    assert view.export_data is False
    assert view.export_structure is False
    assert "关闭视图" in view.reason


def test_view_can_be_excluded():
    result = classify_tables(_tables(), ExcludeConfig(exclude_tables=["v_users"]))
    view = {item.info.name: item for item in result}["v_users"]
    assert view.export_structure is False
    assert view.reason == "未勾选"


def test_blank_regex_ignored():
    assert compile_regexes(["", "  "]) == []


def test_invalid_regex_reports_chinese_error():
    assert validate_regexes([r"([a-"]) is not None
    assert "正则不合法" in validate_regexes([r"([a-"])
    with pytest.raises(RegexError):
        compile_regexes(["("])
