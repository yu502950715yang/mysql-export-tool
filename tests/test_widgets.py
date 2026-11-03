import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.core.models import (DatabaseResult, ExportOptions, ExportReport,
                               TableInfo, TableResult)
from app.ui.dialogs import (BatchExcludeDialog, ConfirmDialog, InputDialog,
                            LogDialog, OptionsDialog, RegexDialog,
                            ReportDialog, TextViewDialog)
from app.ui.widgets import (Card, LogPanel, ProgressWidget, ScrollableTabBar,
                            StatusBadge, TableListWidget)


def test_card_and_status_badge(qapp):
    card = Card("连接")
    assert card.title_label.text() == "连接"
    badge = StatusBadge("未连接")
    assert badge.text() == "● 未连接"
    badge.set_state("ok", "已连接 · MySQL 8.0")
    assert "已连接" in badge.text()
    assert badge.property("state") == "ok"


def test_table_list_check_state_roundtrip(qapp):
    widget = TableListWidget()
    tables = [TableInfo("t1", "table", 3), TableInfo("t2", "table", 0),
              TableInfo("v1", "view")]
    widget.set_tables(tables, excluded={"t2"}, reasons={"t2": "未勾选（仅结构）"})
    assert widget.excluded_names() == ["t2"]
    assert widget.table.item(1, widget.COL_REASON).text() == "未勾选（仅结构）"
    assert widget.checked_count() == 2
    widget.check_all(True)
    assert widget.excluded_names() == []
    widget.invert()
    assert widget.excluded_names() == ["t1", "t2", "v1"]
    widget.update_reasons({"t1": "命中正则 x"})
    assert widget.table.item(0, widget.COL_REASON).text() == "命中正则 x"


def test_progress_widget_states(qapp):
    widget = ProgressWidget()
    widget.set_running(True)
    assert widget.cancel_button.isEnabled() is True
    widget.set_progress(40, "db_a / users")
    assert widget.bar.value() == 40
    assert "db_a / users" in widget.label.text()
    widget.set_idle()
    assert widget.cancel_button.isEnabled() is False
    assert widget.bar.value() == 0


def test_log_panel_append_and_clear(qapp):
    panel = LogPanel()
    panel.append("第一行")
    assert "第一行" in panel.content()
    panel.clear_button.click()
    assert panel.content() == ""


_DIALOG_HOSTS = []


def _dialog_host():
    host = QWidget()
    host.resize(900, 640)
    _DIALOG_HOSTS.append(host)
    return host


def test_regex_dialog_validation(qapp):
    dialog = RegexDialog(_dialog_host(), [r".*_log$"])
    assert dialog.patterns() == [r".*_log$"]
    dialog.editor.setPlainText("(")
    assert dialog.ok_button.isEnabled() is False
    assert "正则不合法" in dialog.hint.text()
    dialog.editor.setPlainText("^tmp_\n\n.*_log$")
    assert dialog.patterns() == ["^tmp_", ".*_log$"]
    assert dialog.ok_button.isEnabled() is True


def test_report_dialog_summary(qapp):
    report = ExportReport(databases=[DatabaseResult(
        db="db1", path="out/db1.sql", tables=[TableResult("t1", "table", 2)])])
    dialog = ReportDialog(_dialog_host(), report)
    assert dialog.table.item(0, 0).text() == "db1"
    assert dialog.table.item(0, 3).text() == "2"


def test_table_list_selection_and_filter(qapp):
    widget = TableListWidget()
    tables = [TableInfo("sys_user", "table", 3), TableInfo("sys_oper_log", "table", 1),
              TableInfo("order_record", "table", 2)]
    widget.set_tables(tables, excluded=set())
    def row_of(name):
        return [item.name for item in widget.tables()].index(name)

    widget.table.selectRow(row_of("sys_oper_log"))
    assert widget.selected_names() == ["sys_oper_log"]
    widget.apply_filter("sys")
    assert widget.table.isRowHidden(row_of("order_record")) is True
    assert widget.table.isRowHidden(row_of("sys_user")) is False
    widget.apply_filter("")
    assert widget.table.isRowHidden(row_of("order_record")) is False


def test_batch_exclude_dialog_parses_names(qapp):
    dialog = BatchExcludeDialog(_dialog_host(), 2)
    dialog.editor.setPlainText("sys_oper_log, sys_logininfor\ndev_collector_data")
    assert dialog.names() == ["sys_oper_log", "sys_logininfor", "dev_collector_data"]
    assert dialog.apply_all() is True
    dialog.editor.setPlainText("  ")
    assert dialog.ok_button.isEnabled() is False


def test_table_list_shows_and_sorts_comments(qapp):
    widget = TableListWidget()
    tables = [TableInfo("b", "table", 1, "订单表"),
              TableInfo("a", "table", 2, "用户表"),
              TableInfo("v", "view", 0, "")]
    widget.set_tables(tables, excluded=set())
    row = [item.name for item in widget.tables()].index("a")
    assert widget.table.item(row, widget.COL_COMMENT).text() == "用户表"
    assert widget.table.item(row, widget.COL_COMMENT).toolTip() == "用户表"
    widget._on_header_clicked(widget.COL_COMMENT)
    assert [item.name for item in widget.tables()] == ["v", "a", "b"]


def test_table_list_header_sort_by_name_and_rows(qapp):
    widget = TableListWidget()
    tables = [TableInfo("b", "table", 100), TableInfo("a", "table", 9),
              TableInfo("v", "view", 0)]
    widget.set_tables(tables, excluded=set())
    assert [item.name for item in widget.tables()] == ["a", "b", "v"]
    widget._on_header_clicked(widget.COL_NAME)
    assert [item.name for item in widget.tables()] == ["a", "b", "v"]
    widget._on_header_clicked(widget.COL_NAME)
    assert [item.name for item in widget.tables()] == ["v", "b", "a"]
    widget._on_header_clicked(widget.COL_ROWS)
    assert [item.est_rows for item in widget.tables()] == [0, 9, 100]
    assert widget.table.horizontalHeader().sortIndicatorSection() == widget.COL_ROWS
    widget.set_tables(tables, excluded={"b"})
    widget._on_header_clicked(widget.COL_ROWS)
    assert widget.excluded_names() == ["b"]
    widget.table.selectRow(0)
    assert widget.selected_names() == [widget.tables()[0].name]


def test_log_dialog_and_confirm(qapp):
    dialog = LogDialog(_dialog_host())
    dialog.set_text("第一行")
    dialog.append_line("第二行")
    assert dialog.content() == "第一行\n第二行"
    dialog.clear_button.click()
    assert dialog.content() == ""

    confirm = ConfirmDialog(_dialog_host(), "确认覆盖", "文件已存在，是否覆盖？",
                            "覆盖", "取消")
    assert confirm.yesButton.text() == "覆盖"
    assert confirm.cancelButton.text() == "取消"


def test_text_view_dialog_content(qapp):
    dialog = TextViewDialog(_dialog_host(), "导出预览", "a 表 100 行")
    assert dialog.content() == "a 表 100 行"
    assert dialog.editor.isReadOnly() is True


def test_table_list_row_count_estimate_and_exact(qapp):
    widget = TableListWidget()
    widget.set_tables([TableInfo("t", "table", 5)], excluded=set())
    assert widget.table.item(0, widget.COL_ROWS).text() == "~5"
    widget.set_row_count("t", 42)
    assert widget.table.item(0, widget.COL_ROWS).text() == "42"
    assert widget.tables()[0].rows_exact is True


def test_scrollable_tab_bar_wheel_scrolls_horizontally(qapp):
    bar = ScrollableTabBar()
    bar.resize(300, 44)
    for index in range(12):
        bar.addTab(f"db_{index}", f"db_{index}")
    bar.show()
    qapp.processEvents()
    scroll_bar = bar.horizontalScrollBar()
    assert scroll_bar.maximum() > 0
    viewport = bar.viewport()
    pos = QPointF(viewport.rect().center())
    event = QWheelEvent(pos, QPointF(viewport.mapToGlobal(viewport.rect().center())),
                        QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewport, event)
    assert scroll_bar.value() > 0


def test_input_dialog_validation(qapp):
    dialog = InputDialog(_dialog_host(), "复制配置", "新配置名：", "Demo 开发库-副本")
    assert dialog.value() == "Demo 开发库-副本"
    assert dialog.ok_button.isEnabled() is True
    dialog.edit.setText("   ")
    assert dialog.ok_button.isEnabled() is False
    dialog.edit.setText("新名字")
    assert dialog.value() == "新名字"


def test_options_dialog_values(qapp):
    dialog = OptionsDialog(_dialog_host(), ExportOptions(
        filename_timestamp=True, escape_unicode=False, batch_size=500))
    assert dialog.timestamp_check.isChecked() is True
    assert dialog.escape_unicode_check.isChecked() is False
    assert dialog.options().batch_size == 500
    dialog.escape_unicode_check.setChecked(True)
    dialog.no_drop_check.setChecked(True)
    options = dialog.options()
    assert options.escape_unicode is True
    assert options.drop_before_create is False
    assert options.filename_timestamp is True


def test_card_is_static_panel(qapp):
    card = Card("连接")
    card.show()
    qapp.processEvents()
    assert card.graphicsEffect() is None
    assert not hasattr(card, "elevatedAni")
    before = card.pos()
    QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
    qapp.processEvents()
    assert card.pos() == before


def test_table_list_resets_scroll_on_set_tables(qapp):
    widget = TableListWidget()
    widget.resize(320, 140)
    widget.show()
    qapp.processEvents()
    tables = [TableInfo(f"t{i}", "table", i, "") for i in range(40)]
    widget.set_tables(tables, excluded=set())
    qapp.processEvents()
    bar = widget.table.verticalScrollBar()
    bar.setValue(bar.maximum())
    assert bar.value() > 0
    widget.set_tables(tables, excluded=set())
    assert bar.value() == 0
