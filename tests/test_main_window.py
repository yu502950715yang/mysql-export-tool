import pytest

pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import QListWidgetItem, QSplitter

from app.core import config as config_mod
from app.core.models import AppConfig, ExcludeConfig, Profile, TableInfo
from app.ui import main_window as main_window_mod
from app.ui.main_window import MainWindow
from app.ui.widgets import StaticCard


@pytest.fixture(autouse=True)
def _disable_auto_row_counts(monkeypatch):
    monkeypatch.setattr(main_window_mod, "AUTO_ROW_COUNTS", False)


def _window(tmp_path):
    return MainWindow(config_path=tmp_path / "config.json")


def test_window_builds_with_default_config(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        assert window.windowTitle().startswith("数据库导出工具")
        assert window.profile_combo.count() == 1
        assert window.table_list.table.rowCount() == 0
        assert window._collect_profile().name == "default"
    finally:
        window.close()


def test_save_and_reload_keeps_connection_fields(qapp, tmp_path):
    path = tmp_path / "config.json"
    window = MainWindow(config_path=path)
    try:
        window.host_edit.setText("db.example.com")
        window.port_spin.setValue(3307)
        window.user_edit.setText("reader")
        window._save_config()
    finally:
        window.close()
    reloaded = MainWindow(config_path=path)
    try:
        assert reloaded.host_edit.text() == "db.example.com"
        assert reloaded.port_spin.value() == 3307
        assert reloaded.user_edit.text() == "reader"
    finally:
        reloaded.close()


def test_unchecked_table_is_persisted_as_exclusion(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._current_db = "db_a"
        window._tables_db = "db_a"
        window._db_excludes.setdefault("db_a", ExcludeConfig())
        window._tables = [TableInfo("t1", "table", 3), TableInfo("t2", "table", 1)]
        window.table_list.set_tables(window._tables, set())
        window.table_list.table.item(1, 0).setCheckState(Qt.Unchecked)
        window._store_current_db_state()
        assert window._db_excludes["db_a"].exclude_tables == ["t2"]
        window._refresh_table_summary()
        assert "仅结构 1" in window.table_summary.text()
    finally:
        window.close()


def test_app_bar_and_config_menu(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        assert window.about_button.text() == "关于"
        assert window.open_config_dir_button.text() == "打开配置目录"
        assert window.config_menu_button.text() == "配置"
        assert window.profile_combo.count() == 1
        assert window.config_path.name == "config.json"
    finally:
        window.close()


def test_theme_applied_and_panels_collapsed_by_default(qapp, tmp_path):
    from qfluentwidgets import PrimaryPushButton

    window = _window(tmp_path)
    try:
        assert isinstance(window.export_button, PrimaryPushButton), "应使用 QFluentWidgets 主按钮"
        assert window.log_button.isCheckable() is False
        assert window.options_button.isCheckable() is False
        assert window._options.batch_size == 1000
    finally:
        window.close()


def test_about_dialog_shows_product_info(qapp, tmp_path, monkeypatch):
    window = _window(tmp_path)
    calls = []

    class FakeInfoDialog:
        def __init__(self, parent, title, message):
            calls.append((title, message))

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_mod, "InfoDialog", FakeInfoDialog)
    try:
        window.about_button.click()
    finally:
        window.close()
    assert calls
    title, text = calls[0]
    assert "数据库导出工具" in title
    assert "v0.1.0" in text
    assert "PySide6" in text and "PyMySQL" in text
    assert ".sql" in text and "排除表" in text


def test_open_config_dir_uses_config_parent(qapp, tmp_path, monkeypatch):
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    window = MainWindow(config_path=config_dir / "config.json")
    opened = []

    class FakeDesktopServices:
        @staticmethod
        def openUrl(url):
            opened.append(url)

    monkeypatch.setattr(main_window_mod, "QDesktopServices", FakeDesktopServices)
    try:
        window.open_config_dir_button.trigger()
    finally:
        window.close()
    assert opened
    assert Path(opened[0].toLocalFile()).resolve() == config_dir.resolve()


def test_open_config_dir_falls_back_to_home_when_missing(qapp, tmp_path, monkeypatch):
    window = MainWindow(config_path=tmp_path / "missing" / "config.json")
    opened = []

    class FakeDesktopServices:
        @staticmethod
        def openUrl(url):
            opened.append(url)

    monkeypatch.setattr(main_window_mod, "QDesktopServices", FakeDesktopServices)
    try:
        window.open_config_dir_button.trigger()
    finally:
        window.close()
    assert opened
    assert Path(opened[0].toLocalFile()).resolve() == Path.home().resolve()


def test_stale_table_state_not_written_to_new_database(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._current_db = "db_a"
        window._tables_db = "db_a"
        window._db_excludes["db_a"] = ExcludeConfig(exclude_tables=["audit_log"])
        window._on_tables_loaded("db_a", [TableInfo("audit_log", "table", 1),
                                          TableInfo("users", "table", 3)])
        assert window.table_list.excluded_names() == ["audit_log"]

        # 切库尚未完成：table_list 仍是 db_a 的内容，但 _current_db 已是 db_b
        window._current_db = "db_b"
        window._store_current_db_state()
        assert window._db_excludes.get("db_b", ExcludeConfig()).exclude_tables == []

        window._on_tables_loaded("db_b", [TableInfo("users", "table", 3)])
        assert window._tables_db == "db_b"
        assert window.table_list.excluded_names() == []
        assert window._db_excludes["db_a"].exclude_tables == ["audit_log"]
    finally:
        window.close()


def test_start_export_uses_profile_snapshot_and_disables_editors(qapp, tmp_path, monkeypatch):
    window = _window(tmp_path)
    captured = {}

    class FakeSignal:
        def connect(self, _slot):
            pass

    class FakeExportWorker:
        def __init__(self, profile, plans, options, outdir, parent=None):
            captured["profile"] = profile
            captured["options"] = options
            captured["parent"] = parent
            self.sig_log = FakeSignal()
            self.sig_progress = FakeSignal()
            self.sig_finished = FakeSignal()
            self.sig_error = FakeSignal()
            self.finished = FakeSignal()

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(main_window_mod, "ExportWorker", FakeExportWorker)
    try:
        window.host_edit.setText("db.example.com")
        window.user_edit.setText("reader")
        item = QListWidgetItem("db_a")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        window.database_list.addItem(item)
        window.outdir_edit.setText(str(tmp_path / "out"))
        window._start_export()

        # worker 拿到 profile 快照，导出中改界面不会影响它
        window.host_edit.setText("changed.example.com")
        window._collect_profile()
        worker_profile = captured["profile"]
        assert worker_profile.host == "db.example.com"
        assert worker_profile.user == "reader"
        assert captured["options"] is worker_profile.options
        assert captured["parent"] is window

        # 导出期间连接区、输出目录与配置管理被禁用
        assert window.host_edit.isEnabled() is False
        assert window.port_spin.isEnabled() is False
        assert window.password_edit.isEnabled() is False
        assert window.outdir_edit.isEnabled() is False
        assert window.profile_combo.isEnabled() is False
        assert window.save_button.isEnabled() is False

        window._set_exporting(False)
        assert window.host_edit.isEnabled() is True
        assert window.profile_combo.isEnabled() is True
    finally:
        window.close()


def _add_database_item(window, name, checked=True):
    item = QListWidgetItem(name)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    window.database_list.addItem(item)
    return item


def test_database_tabs_switch_and_render(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables["db_a"] = [TableInfo("t1", "table", 3)]
        window._db_tables["db_b"] = [TableInfo("t2", "table", 4)]
        window.database_list.blockSignals(True)
        _add_database_item(window, "db_a")
        _add_database_item(window, "db_b")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        assert window.database_tabs.count() == 2
        assert window._current_db == "db_a"
        assert window.table_list.tables()[0].name == "t1"
        window._activate_database("db_b")
        assert window._current_db == "db_b"
        assert window.table_list.tables()[0].name == "t2"
    finally:
        window.close()


def test_filter_and_exclude_selected(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables["db_a"] = [TableInfo("sys_user", "table", 3),
                                      TableInfo("sys_oper_log", "table", 1),
                                      TableInfo("order_record", "table", 2)]
        window.database_list.blockSignals(True)
        _add_database_item(window, "db_a")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        window.table_filter.setText("sys")

        def row_of(name):
            return [item.name for item in window.table_list.tables()].index(name)

        assert window.table_list.table.isRowHidden(row_of("order_record")) is True
        assert window.table_list.table.isRowHidden(row_of("sys_user")) is False
        window.table_list.table.selectRow(row_of("sys_user"))
        window._exclude_selected()
        assert window._db_excludes["db_a"].exclude_tables == ["sys_user"]
        window.table_filter.setText("")
        assert "仅结构 1" in window.table_summary.text()
    finally:
        window.close()


def test_batch_exclude_applies_to_all_checked_databases(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables["db_a"] = [TableInfo("t1", "table", 3)]
        window._db_tables["db_b"] = [TableInfo("t2", "table", 4)]
        window.database_list.blockSignals(True)
        _add_database_item(window, "db_a")
        _add_database_item(window, "db_b")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        for db in ("db_a", "db_b"):
            window._add_excluded_names(db, ["sys_oper_log"])
        assert window._db_excludes["db_a"].exclude_tables == ["sys_oper_log"]
        assert window._db_excludes["db_b"].exclude_tables == ["sys_oper_log"]
    finally:
        window.close()


def test_row_counts_start_and_apply(monkeypatch, qapp, tmp_path):
    monkeypatch.setattr(main_window_mod, "AUTO_ROW_COUNTS", True)

    class FakeRowCountWorker(QObject):
        sig_progress = Signal(str, str, int, int, int)
        sig_skipped = Signal(str, str, str)
        sig_done = Signal(str, object)
        started = []

        def __init__(self, profile, db, tables, parent=None):
            super().__init__(parent)
            self.db = db
            self.tables = list(tables)

        def start(self):
            FakeRowCountWorker.started.append(self)

        def cancel(self):
            pass

    monkeypatch.setattr(main_window_mod, "RowCountWorker", FakeRowCountWorker)
    window = _window(tmp_path)
    try:
        window._db_tables["db_a"] = [TableInfo("t1", "table", 5)]
        window.database_list.blockSignals(True)
        _add_database_item(window, "db_a")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        assert FakeRowCountWorker.started
        assert FakeRowCountWorker.started[0].db == "db_a"
        assert FakeRowCountWorker.started[0].tables == ["t1"]

        window._on_row_count_progress("db_a", "t1", 42, 1, 1)
        info = window._db_tables["db_a"][0]
        assert info.rows_exact is True
        assert info.est_rows == 42
        assert window.table_list.table.item(0, window.table_list.COL_ROWS).text() == "42"

        window._on_row_count_done("db_a", {"t1": 42})
        assert window.row_count_label.text() == ""
    finally:
        window.close()


def test_saved_database_selection_restored_after_connect(qapp, tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    profile = Profile(name="dev", host="db.example.com", user="reader",
                      selected_databases=["db_a", "db_b"])
    config_mod.save_config(AppConfig(active_profile="dev", profiles=[profile]), config_path)
    window = MainWindow(config_path=config_path)
    monkeypatch.setattr(window, "_ensure_tables_loaded", lambda db: None)
    try:
        # 连接/刷新前都会 _collect_profile，此时列表还没加载，不能覆盖已保存的选择
        window._collect_profile()
        assert window.config.profile("dev").selected_databases == ["db_a", "db_b"]

        window._on_databases_loaded(["db_a", "db_b", "db_c"])
        states = {window.database_list.item(i).text(): window.database_list.item(i).checkState()
                  for i in range(window.database_list.count())}
        assert states == {"db_a": Qt.CheckState.Checked,
                          "db_b": Qt.CheckState.Checked,
                          "db_c": Qt.CheckState.Unchecked}
        assert window._current_db == "db_a"
        assert window.database_list.currentItem().text() == "db_a"

        # 用户取消勾选后保存，会写入当前列表状态
        window.database_list.item(0).setCheckState(Qt.CheckState.Unchecked)
        window._collect_profile()
        assert window.config.profile("dev").selected_databases == ["db_b"]
    finally:
        window.close()


def test_many_databases_use_scrollable_closable_tabs(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables = {f"db_{i}": [TableInfo("t", "table", 1)] for i in range(8)}
        window.database_list.blockSignals(True)
        for i in range(8):
            _add_database_item(window, f"db_{i}")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        assert window.database_tabs.isHidden() is False
        assert window.database_tabs.count() == 8
        assert window.database_tabs.isScrollable() is True
        assert window.database_tabs.currentIndex() == 0
    finally:
        window.close()


def test_closing_tab_unchecks_database(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables = {"db_a": [TableInfo("t", "table", 1)],
                             "db_b": [TableInfo("t2", "table", 2)]}
        window.database_list.blockSignals(True)
        _add_database_item(window, "db_a")
        _add_database_item(window, "db_b")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        assert window.database_tabs.count() == 2

        window._on_tab_close_requested(1)  # 关闭 db_b
        qapp.processEvents()
        item = window.database_list.item(1)
        assert item.text() == "db_b"
        assert item.checkState() == Qt.CheckState.Unchecked
        assert window.database_tabs.count() == 1
        assert window.database_tabs.tabText(0) == "db_a"
    finally:
        window.close()


def test_left_click_switches_tab(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables = {"db_a": [TableInfo("t", "table", 1)],
                             "db_b": [TableInfo("t", "table", 2)],
                             "db_c": [TableInfo("t", "table", 3)]}
        window.database_list.blockSignals(True)
        for name in ("db_a", "db_b", "db_c"):
            _add_database_item(window, name)
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        assert window.database_tabs.currentIndex() == 0

        window.database_list.setCurrentRow(2)  # 左侧点击 db_c
        qapp.processEvents()
        assert window._current_db == "db_c"
        assert window.database_tabs.currentIndex() == 2
        assert window.database_tabs.tabText(2) == "db_c"
    finally:
        window.close()


def test_tab_scrollbar_visible_and_synced(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window._db_tables = {f"db_{i}": [] for i in range(9)}
        window.database_list.blockSignals(True)
        for i in range(9):
            _add_database_item(window, f"db_{i}")
        window.database_list.blockSignals(False)
        window._rebuild_database_tabs()
        window.show()
        qapp.processEvents()
        qapp.processEvents()
        scrollbar = window.tab_scrollbar
        inner = window.database_tabs.horizontalScrollBar()
        window._sync_tab_scrollbar()
        assert inner.maximum() > 0
        assert scrollbar.isVisible() is True
        assert scrollbar.maximum() == inner.maximum()
        scrollbar.setValue(120)
        assert inner.value() == 120
        inner.setValue(40)
        assert scrollbar.value() == 40
    finally:
        window.close()


def test_action_bar_uses_static_card(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        assert window.findChildren(StaticCard)
    finally:
        window.close()


def test_workspace_uses_fixed_left_layout(qapp, tmp_path):
    window = _window(tmp_path)
    try:
        window.show()
        qapp.processEvents()
        assert window.workspace.width() > 0
        assert window.workspace.width() <= window.centralWidget().width()
        assert window.table_card.width() > window.database_card.width()
        assert not window.findChildren(QSplitter)
    finally:
        window.close()
