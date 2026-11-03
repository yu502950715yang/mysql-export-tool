"""生成界面预览截图（offscreen 渲染，不连数据库）。

用法：
    python docs/design/capture_ui.py
输出：
    docs/design/ui-empty.png     未连接空态
    docs/design/ui-loaded.png    已连接、已加载库表的典型状态
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.core import config as config_mod
from app.core.models import (AppConfig, ExcludeConfig, ExportOptions, Profile,
                             TableInfo)
from app.ui.main_window import MainWindow

OUT_DIR = Path(__file__).resolve().parent
DATABASES = ["demo_shop_system", "demo_shop", "demo_shop_report"]
TABLES = [
    TableInfo("sys_user", "table", 26, "用户账号表"),
    TableInfo("sys_dept", "table", 18, "部门表"),
    TableInfo("sys_role", "table", 9, "角色表"),
    TableInfo("sys_menu", "table", 71, "菜单权限表"),
    TableInfo("sys_dict_data", "table", 134, "字典数据"),
    TableInfo("sys_oper_log", "table", 128_416, "操作日志"),
    TableInfo("sys_logininfor", "table", 42_318, "登录日志"),
    TableInfo("client_terminal_log", "table", 9_204, "终端日志"),
    TableInfo("v_sys_user_dept", "view", 0, "用户部门视图"),
]

BUSINESS_TABLES = [
    TableInfo("school_info", "table", 21_834, "学校基础信息"),
    TableInfo("school_temp_user_info", "table", 512_406, "临时用户信息"),
    TableInfo("order_record", "table", 88_102, "订单记录"),
    TableInfo("order_record_202601", "table", 32_004),
    TableInfo("dev_collector_data", "table", 920_331, "采集原始数据"),
    TableInfo("tmp_udp_realtime", "table", 4_512),
    TableInfo("v_order_summary", "view", 0, "订单汇总视图"),
]


def _make_config(tmp: Path) -> Path:
    profile = Profile(
        name="dev", host="127.0.0.1", port=33061, user="demo",
        password="demo-password",
        databases={"demo_shop_system": ExcludeConfig(exclude_regexes=[".*_log$"])},
        selected_databases=DATABASES[:2],
        options=ExportOptions(filename_timestamp=True),
    )
    path = tmp / "config.json"
    config_mod.save_config(AppConfig(active_profile="dev", profiles=[profile]), path)
    return path


def _fill_loaded_state(window: MainWindow) -> None:
    """模拟已连接、已加载库表的状态，不触发网络线程。"""
    window.connection_status.set_state("ok", "已连接 · MySQL 8.0.36")
    window.host_edit.setText("127.0.0.1")
    window.port_spin.setValue(33061)
    window.user_edit.setText("demo")
    window.password_edit.setText("demo-password")
    window.database_list.blockSignals(True)
    for index, name in enumerate(DATABASES):
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if index < 2 else Qt.CheckState.Unchecked)
        item.setSizeHint(QSize(0, 36))
        window.database_list.addItem(item)
    window.database_list.setCurrentRow(0)
    window.database_list.blockSignals(False)
    window._show_database_list()
    for table in TABLES + BUSINESS_TABLES:
        table.rows_exact = True
    window._db_tables[DATABASES[0]] = TABLES
    window._db_tables[DATABASES[1]] = BUSINESS_TABLES
    window._rebuild_database_tabs()
    window._activate_database(DATABASES[0])
    window.table_list._on_header_clicked(window.table_list.COL_NAME)
    window.status_label.setText("已连接 · 3 个数据库")


EXTRA_DATABASES = ["demo_erp", "demo_bi", "demo_hr", "demo_hr_system",
                   "demo_crm", "demo_report", "demo_legacy"]


def _fill_many_state(window: MainWindow) -> None:
    """勾选 9 个库：超过阈值后 Tab 自动换成下拉选择。"""
    _fill_loaded_state(window)
    window.database_list.blockSignals(True)
    for name in EXTRA_DATABASES:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setSizeHint(QSize(0, 36))
        window.database_list.addItem(item)
    window.database_list.blockSignals(False)
    window._rebuild_database_tabs()
    window.status_label.setText("已连接 · 32 个数据库")


def _capture(window: MainWindow, name: str) -> Path:
    window.show()
    app = QApplication.instance()
    for _ in range(3):
        app.processEvents()
    path = OUT_DIR / name
    window.grab().save(str(path))
    window.close()
    return path


def _fill_expanded_state(window: MainWindow) -> None:
    """展示「导出设置」展开、导出进行中的状态。"""
    _fill_loaded_state(window)
    for line in ("连接成功：MySQL 8.0.36", "已加载 3 个数据库",
                 "===== 数据库 demo_shop_system =====",
                 "    [导出] sys_user 26 行", "    [导出] sys_dept 18 行"):
        window._log(line)
    window.progress_container.setVisible(True)
    window.progress.set_running(True)
    window.progress.set_progress(46, "demo_shop_system / sys_user · 12,345 行 · 3.2 秒")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    with tempfile.TemporaryDirectory(prefix="mysql-export-shot-") as tmp:
        tmp_path = Path(tmp)
        empty = MainWindow(config_path=_make_config(tmp_path / "empty"))
        empty.host_edit.setText("127.0.0.1")
        empty.port_spin.setValue(33061)
        empty.user_edit.setText("demo")
        print("已生成:", _capture(empty, "ui-empty.png"))

        loaded = MainWindow(config_path=_make_config(tmp_path / "loaded"))
        _fill_loaded_state(loaded)
        print("已生成:", _capture(loaded, "ui-loaded.png"))

        expanded = MainWindow(config_path=_make_config(tmp_path / "expanded"))
        _fill_expanded_state(expanded)
        print("已生成:", _capture(expanded, "ui-expanded.png"))

        many = MainWindow(config_path=_make_config(tmp_path / "many"))
        _fill_many_state(many)
        print("已生成:", _capture(many, "ui-many-dbs.png"))
    app.quit()


if __name__ == "__main__":
    main()
