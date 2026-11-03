"""主窗口：配置管理、连接、库/表选择、排除规则、导出与日志（QFluentWidgets 版）。"""
from __future__ import annotations

import copy
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QScrollBar, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, CheckBox, ComboBox,
                            FluentIcon as FIF, IconWidget, LineEdit, PasswordLineEdit,
                            DropDownPushButton, PrimaryPushButton, PushButton, RoundMenu,
                            SearchLineEdit,
                            SpinBox, StrongBodyLabel, TabCloseButtonDisplayMode,
                            Theme, TransparentPushButton, setTheme, setThemeColor)

from app import APP_NAME, APP_TITLE, __version__
from app.core import config as config_mod
from app.core.classify import classify_tables
from app.core.models import (DatabasePlan, ExcludeConfig, ExportOptions, Profile,
                             STATUS_CANCELLED)
from app.core.plan import build_plan
from app.core.runner import output_path_for
from app.dialects import dialect_label
from app.ui.dialogs import (BatchExcludeDialog, ConfirmDialog, ErrorDialog,
                            InfoDialog, InputDialog, LogDialog, OptionsDialog,
                            RegexDialog, ReportDialog, TextViewDialog)
from app.ui.widgets import (Card, EmptyHint, LogPanel, ProgressWidget, ScrollableTabBar,
                            StaticCard, StatusBadge, TableListWidget)
from app.ui.workers import (DatabasesWorker, ExportWorker, PingWorker, PreviewWorker,
                            RowCountWorker, TablesWorker)

PAGE_BACKGROUND = "#F3F4F6"
AUTO_ROW_COUNTS = True  # 测试可关闭，避免触发真实数据库线程


class MainWindow(QMainWindow):
    """单窗口应用：顶部配置栏、连接卡片、左库右表、底部导出栏。"""

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        setTheme(Theme.LIGHT)
        setThemeColor("#2563EB")
        self.config_path = Path(config_path) if config_path else config_mod.default_config_path()
        self.config, warnings = config_mod.load_config(self.config_path)
        self._tables: list = []
        self._tables_db: str | None = None
        self._current_db: str | None = None
        self._db_excludes: dict[str, ExcludeConfig] = {}
        self._db_tables: dict[str, list] = {}
        self._db_loading: set[str] = set()
        self._loading_started = 0.0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(500)
        self._loading_timer.timeout.connect(self._on_loading_tick)
        self._worker = None
        self._file_handler = None
        self._log_dialog: LogDialog | None = None
        self._options = ExportOptions()
        self._row_count_worker: RowCountWorker | None = None
        self._row_count_db: str | None = None
        self._row_count_started: set[str] = set()
        self._database_loaded = False  # 列表未加载前，_collect_profile 不能覆盖已保存的勾选
        self._current_outdir: Path | None = None
        self._logger = logging.getLogger("export")
        self._active_name = self.config.active_profile
        self.setWindowTitle("%s v%s" % (APP_TITLE, __version__))
        self.resize(1240, 860)
        self.setMinimumSize(1040, 660)
        self._build_ui()
        self._load_profiles()
        for warning in warnings:
            self._log("提示：" + warning)
        self._log("配置文件：%s" % self.config_path)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        central.setStyleSheet("QWidget#Root { background: %s; }" % PAGE_BACKGROUND)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        outer.addLayout(self._build_app_bar())
        outer.addWidget(self._build_connection_card())
        outer.addWidget(self._build_workspace(), 1)
        outer.addWidget(self._build_action_bar())

    def _build_app_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)
        logo = IconWidget(FIF.DOCUMENT)
        logo.setFixedSize(20, 20)
        bar.addWidget(logo)
        bar.addWidget(StrongBodyLabel(APP_TITLE))
        version = CaptionLabel("v%s" % __version__)
        version.setTextColor("#9CA3AF", "#9CA3AF")
        bar.addWidget(version)
        bar.addStretch(1)

        self.profile_combo = ComboBox()
        self.profile_combo.setMinimumWidth(150)
        self.profile_combo.setToolTip("当前配置（在「配置」菜单中管理）")
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        bar.addWidget(self.profile_combo)

        self.config_menu = RoundMenu(title="", parent=self)
        self._build_config_menu()
        self.config_menu_button = DropDownPushButton("配置", icon=FIF.SETTING)
        self.config_menu_button.setMenu(self.config_menu)
        bar.addWidget(self.config_menu_button)

        self.about_button = TransparentPushButton("关于", icon=FIF.INFO)
        self.about_button.clicked.connect(self._show_about)
        bar.addWidget(self.about_button)
        return bar

    def _build_config_menu(self) -> None:
        self.new_button = QAction("新建配置", self)
        self.copy_button = QAction("复制当前配置", self)
        self.rename_button = QAction("重命名当前配置", self)
        self.delete_button = QAction("删除当前配置", self)
        self.save_button = QAction("保存配置", self)
        self.open_config_dir_button = QAction("打开配置目录", self)
        self.new_button.triggered.connect(self._new_profile)
        self.copy_button.triggered.connect(self._copy_profile)
        self.rename_button.triggered.connect(self._rename_profile)
        self.delete_button.triggered.connect(self._delete_profile)
        self.save_button.triggered.connect(self._save_config)
        self.open_config_dir_button.triggered.connect(self._open_config_dir)
        self.config_menu.addAction(self.new_button)
        self.config_menu.addAction(self.copy_button)
        self.config_menu.addAction(self.rename_button)
        self.config_menu.addAction(self.delete_button)
        self.config_menu.addSeparator()
        self.config_menu.addAction(self.save_button)
        self.config_menu.addAction(self.open_config_dir_button)

    def _build_connection_card(self) -> Card:
        card = Card("连接")
        self.connection_status = StatusBadge("未连接")
        card.add_header_widget(self.connection_status)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.host_edit = LineEdit()
        self.host_edit.setPlaceholderText("主机地址")
        self.host_edit.setToolTip("MySQL 服务器地址")
        self.host_edit.setMinimumWidth(180)
        self.port_spin = SpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(3306)
        self.port_spin.setFixedWidth(150)
        self.port_spin.setToolTip("端口")
        self.user_edit = LineEdit()
        self.user_edit.setPlaceholderText("用户名")
        self.user_edit.setMinimumWidth(130)
        self.password_edit = PasswordLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setMinimumWidth(150)
        self.connect_button = PrimaryPushButton("连接", icon=FIF.SYNC)
        self.connect_button.setMinimumWidth(100)
        self.connect_button.setToolTip("连接成功后自动加载数据库列表")
        self.connect_button.clicked.connect(self._test_connection)
        self.test_button = self.connect_button  # 兼容旧调用
        row.addWidget(self.host_edit, 2)
        row.addWidget(self.port_spin)
        row.addWidget(self.user_edit, 1)
        row.addWidget(self.password_edit, 1)
        row.addWidget(self.connect_button)
        card.add_layout(row)

        self.dialect_label = QLabel("MySQL")
        self.dialect_label.setVisible(False)
        return card

    def _build_workspace(self) -> QWidget:
        # 用固定左侧 + 右侧自适应的普通布局，避免 QSplitter 在切换 Tab 后保留旧的像素尺寸
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.database_card = self._build_database_card()
        self.table_card = self._build_table_card()
        self.database_card.setFixedWidth(340)
        layout.addWidget(self.database_card, 0)
        layout.addWidget(self.table_card, 1)
        self.workspace = container
        return container

    def _build_database_card(self) -> Card:
        card = Card("数据库")
        self.refresh_button = TransparentPushButton("刷新", icon=FIF.SYNC)
        self.refresh_button.setToolTip("重新加载数据库列表")
        self.refresh_button.clicked.connect(self._refresh_databases)
        self.system_db_check = CheckBox("系统库")
        self.system_db_check.setChecked(self.config.ui.show_system_dbs)
        self.system_db_check.setToolTip("显示系统数据库（information_schema、mysql 等）")
        card.add_header_widget(self.refresh_button)
        card.add_header_widget(self.system_db_check)

        self.database_list = QListWidget()
        self.database_list.itemChanged.connect(self._on_database_checked)
        self.database_list.currentItemChanged.connect(self._on_database_highlighted)
        self.database_hint = EmptyHint("连接后加载数据库")
        self.database_stack = QStackedWidget()
        self.database_stack.addWidget(self.database_hint)
        self.database_stack.addWidget(self.database_list)
        card.add_widget(self.database_stack, 1)
        return card

    def _build_table_card(self) -> Card:
        card = Card("表与视图")
        self.select_all_button = TransparentPushButton("全选", icon=FIF.ACCEPT)
        self.select_none_button = TransparentPushButton("清空", icon=FIF.REMOVE)
        self.regex_button = TransparentPushButton("正则", icon=FIF.FILTER)
        self.select_all_button.setToolTip("当前库全部勾选：导出所有表数据")
        self.select_none_button.setToolTip("当前库全部取消：所有表只保留建表语句")
        self.regex_button.setToolTip("按正则排除表（可应用到所有已勾选库）")
        self.select_all_button.clicked.connect(lambda: self._bulk_check("all"))
        self.select_none_button.clicked.connect(lambda: self._bulk_check("none"))
        self.regex_button.clicked.connect(self._edit_regexes)
        card.add_header_widget(self.select_all_button)
        card.add_header_widget(self.select_none_button)
        card.add_header_widget(self.regex_button)

        # 每个已勾选的库一个 Tab，切换库不用回到左侧列表
        self.database_tabs = ScrollableTabBar()
        self.database_tabs.tabBarClicked.connect(self._tab_clicked)
        self.database_tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.database_tabs.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.ON_HOVER)
        self.database_tabs.setAddButtonVisible(False)
        self.database_tabs.setMovable(False)
        self.database_tabs.setScrollable(True)
        self.database_tabs.setVisible(False)
        card.add_widget(self.database_tabs)

        # TabBar 自带的横向滚动条被组件库固定隐藏，这里加一条独立细滚动条联动
        self.tab_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.tab_scrollbar.setFixedHeight(8)
        self.tab_scrollbar.setStyleSheet(
            "QScrollBar:horizontal{background:transparent;height:8px;margin:0;}"
            "QScrollBar::handle:horizontal{background:#C7CBD1;border-radius:3px;min-width:28px;}"
            "QScrollBar::handle:horizontal:hover{background:#A8AEB6;}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}"
            "QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent;}")
        self.tab_scrollbar.setVisible(False)
        inner_bar = self.database_tabs.horizontalScrollBar()
        inner_bar.rangeChanged.connect(lambda *_: self._sync_tab_scrollbar())
        inner_bar.valueChanged.connect(self._on_tab_inner_scrolled)
        self.tab_scrollbar.valueChanged.connect(self._on_tab_scrollbar_scrolled)
        card.add_widget(self.tab_scrollbar)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.table_filter = SearchLineEdit()
        self.table_filter.setPlaceholderText("搜索表名")
        self.table_filter.setClearButtonEnabled(True)
        self.table_filter.setFixedWidth(190)
        self.table_filter.setToolTip("按表名过滤当前库的表")
        self.table_filter.textChanged.connect(self._on_filter_changed)
        self.exclude_selected_button = TransparentPushButton("排除选中", icon=FIF.REMOVE)
        self.exclude_selected_button.setToolTip("把表清单中选中的行排除（仅保留建表语句）")
        self.exclude_selected_button.clicked.connect(self._exclude_selected)
        self.batch_exclude_button = TransparentPushButton("批量排除", icon=FIF.EDIT)
        self.batch_exclude_button.setToolTip("粘贴一批表名，快速排除")
        self.batch_exclude_button.clicked.connect(self._batch_exclude)
        toolbar.addWidget(self.table_filter)
        toolbar.addWidget(self.exclude_selected_button)
        toolbar.addWidget(self.batch_exclude_button)
        self.row_count_label = CaptionLabel("")
        self.row_count_label.setTextColor("#6B7280", "#6B7280")
        toolbar.addWidget(self.row_count_label)
        toolbar.addStretch(1)
        card.add_layout(toolbar)

        self.table_list = TableListWidget()
        self.table_list.table.itemChanged.connect(self._on_table_checked)
        self.table_hint = EmptyHint("勾选左侧数据库后查看表")
        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table_hint)
        self.table_stack.addWidget(self.table_list)
        card.add_widget(self.table_stack, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        self.table_summary = CaptionLabel("未加载")
        self.table_summary.setTextColor("#6B7280", "#6B7280")
        footer.addWidget(self.table_summary)
        footer.addStretch(1)
        card.add_layout(footer)
        return card

    def _build_action_bar(self) -> QWidget:
        bar = StaticCard()
        bar.setBorderRadius(10)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        outdir_label = CaptionLabel("输出到")
        outdir_label.setTextColor("#6B7280", "#6B7280")
        self.outdir_edit = LineEdit()
        self.outdir_edit.setText(self.config.ui.last_outdir
                                 or str(config_mod.default_export_dir()))
        self.outdir_edit.setToolTip("导出的 .sql 文件保存目录")
        self.browse_button = PushButton("浏览", icon=FIF.FOLDER)
        self.browse_button.clicked.connect(self._browse_outdir)
        self.options_button = PushButton("导出设置", icon=FIF.SETTING)
        self.options_button.setToolTip("时间戳 / DROP / 编码 / 批量大小")
        self.options_button.clicked.connect(self._edit_options)
        self.preview_button = PushButton("预览", icon=FIF.VIEW)
        self.preview_button.setToolTip("预览导出清单，不写文件")
        self.preview_button.clicked.connect(self._preview)
        self.export_button = PrimaryPushButton("开始导出", icon=FIF.PLAY)
        self.export_button.setMinimumWidth(120)
        self.export_button.clicked.connect(self._start_export)
        row.addWidget(outdir_label)
        row.addWidget(self.outdir_edit, 1)
        row.addWidget(self.browse_button)
        row.addWidget(self.options_button)
        row.addWidget(self.preview_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)

        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress = ProgressWidget()
        self.progress.cancel_button.clicked.connect(self._cancel_export)
        progress_layout.addWidget(self.progress)
        self.progress_container.setVisible(False)
        layout.addWidget(self.progress_container)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.status_label = CaptionLabel("就绪")
        self.status_label.setTextColor("#6B7280", "#6B7280")
        self.log_button = PushButton("日志", icon=FIF.DOCUMENT)
        self.log_button.setToolTip("打开运行日志窗口")
        self.log_button.clicked.connect(self._open_log)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.log_button)
        layout.addLayout(footer)

        self.log_panel = LogPanel(self)  # 仅作日志缓冲，展示在独立窗口
        self.log_panel.setVisible(False)
        return bar

    def _edit_options(self) -> None:
        dialog = OptionsDialog(self, self._options)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._options = dialog.options()
        self.status_label.setText("导出设置已更新")
        self._log("导出设置：时间戳=%s，DROP=%s，中文转义=%s，批量=%d"
                  % (self._options.filename_timestamp, self._options.drop_before_create,
                     self._options.escape_unicode, self._options.batch_size))

    def _open_log(self) -> None:
        if self._log_dialog is None:
            self._log_dialog = LogDialog(self)
        self._log_dialog.set_text(self.log_panel.content())
        self._log_dialog.exec()

    # -------------------------------------------------------------- 配置
    def _load_profiles(self) -> None:
        config_mod.ensure_active_profile(self.config)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in self.config.profiles:
            self.profile_combo.addItem(profile.name)
        index = self.profile_combo.findText(self.config.active_profile)
        self.profile_combo.setCurrentIndex(max(0, index))
        self.profile_combo.blockSignals(False)
        self._active_name = self.config.active_profile
        self._apply_profile(self.config.profile())

    def _apply_profile(self, profile: Profile | None) -> None:
        if profile is None:
            return
        self.config.active_profile = profile.name
        self._db_excludes = {
            db: ExcludeConfig(list(cfg.exclude_tables), list(cfg.exclude_regexes))
            for db, cfg in profile.databases.items()
        }
        self._db_tables.clear()
        self._db_loading.clear()
        self._cancel_row_count()
        self._row_count_started.clear()
        self._database_loaded = False
        self._current_db = None
        self.database_list.blockSignals(True)
        self.database_list.clear()
        self.database_list.blockSignals(False)
        self.database_tabs.blockSignals(True)
        self.database_tabs.clear()
        self.database_tabs.blockSignals(False)
        self.database_tabs.setVisible(False)
        self.table_filter.blockSignals(True)
        self.table_filter.clear()
        self.table_filter.blockSignals(False)
        self._tables = []
        self._tables_db = None
        self.table_list.set_tables([], set())
        self.table_summary.setText("")
        self._show_database_hint("连接后加载数据库")
        self._show_table_hint("勾选左侧数据库后查看表")
        self.host_edit.setText(profile.host)
        self.port_spin.setValue(profile.port or 3306)
        self.user_edit.setText(profile.user)
        self.password_edit.setText(profile.password)
        self.dialect_label.setText(dialect_label(profile.dialect))
        self._options = ExportOptions(**profile.options.to_dict())
        self.connection_status.set_state("idle", "未连接")
        self.status_label.setText("就绪")
        self._log("切换到配置：%s" % profile.name)

    def _collect_profile(self, name: str | None = None) -> Profile | None:
        name = name or self._active_name or self.profile_combo.currentText()
        profile = self.config.profile(name)
        if profile is None:
            return None
        profile.host = self.host_edit.text().strip()
        profile.port = int(self.port_spin.value())
        profile.user = self.user_edit.text().strip()
        profile.password = self.password_edit.text()
        self._store_current_db_state()
        profile.databases = {
            db: ExcludeConfig(list(cfg.exclude_tables), list(cfg.exclude_regexes))
            for db, cfg in self._db_excludes.items()
        }
        if self._database_loaded:
            profile.selected_databases = [
                self.database_list.item(index).text()
                for index in range(self.database_list.count())
                if self.database_list.item(index).checkState() == Qt.CheckState.Checked
            ]
        profile.options = ExportOptions(**self._options.to_dict())
        self.config.ui.last_outdir = self.outdir_edit.text().strip()
        self.config.ui.show_system_dbs = self.system_db_check.isChecked()
        return profile

    def _save_config(self) -> None:
        self._collect_profile()
        try:
            config_mod.save_config(self.config, self.config_path)
        except OSError as exc:
            self._show_error("配置保存失败", str(exc))
            return
        self._log("配置已保存：%s" % self.config_path)
        self.status_label.setText("配置已保存")

    def _open_config_dir(self) -> None:
        """打开配置文件所在目录；目录不存在时退化为用户主目录。"""
        target = self.config_path.expanduser().resolve().parent
        if not target.is_dir():
            target = Path.home()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _show_about(self) -> None:
        """显示产品、版本与技术栈信息。"""
        InfoDialog(
            self, "关于 %s" % APP_TITLE,
            "%s v%s\n\n技术栈：PySide6 + QFluentWidgets + PyMySQL\n"
            "输出格式：每库一个 .sql 文件；排除表仅输出建表语句，不输出数据"
            % (APP_TITLE, __version__)).exec()

    def _on_profile_changed(self, index: int) -> None:
        if index < 0:
            return
        self._collect_profile(self._active_name)
        name = self.profile_combo.itemText(index)
        profile = self.config.profile(name)
        if profile is None:
            return
        self._active_name = name
        self._apply_profile(profile)

    def _ask_text(self, title: str, label: str, text: str = ""):
        """Fluent 单行输入框，返回 (文本, 是否确定)。"""
        dialog = InputDialog(self, title, label, text)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return "", False
        return dialog.value(), True

    def _new_profile(self) -> None:
        name, ok = self._ask_text("新建配置", "配置名：")
        name = (name or "").strip()
        if not ok or not name:
            return
        if self.config.profile(name) is not None:
            self._show_error("配置已存在", name)
            return
        self._collect_profile(self._active_name)
        self.config.profiles.append(Profile(name=name))
        self.config.active_profile = name
        self._active_name = name
        self._load_profiles()
        self._save_config()

    def _copy_profile(self) -> None:
        self._collect_profile(self._active_name)
        current = self.config.profile(self._active_name)
        if current is None:
            return
        name, ok = self._ask_text("复制配置", "新配置名：", current.name + "-副本")
        name = (name or "").strip()
        if not ok or not name:
            return
        if self.config.profile(name) is not None:
            self._show_error("配置已存在", name)
            return
        clone = Profile(
            name=name, dialect=current.dialect, host=current.host, port=current.port,
            user=current.user, password=current.password, charset=current.charset,
            connect_timeout=current.connect_timeout,
            databases={db: ExcludeConfig(list(cfg.exclude_tables), list(cfg.exclude_regexes))
                       for db, cfg in current.databases.items()},
            selected_databases=list(current.selected_databases),
            options=ExportOptions(**current.options.to_dict()),
        )
        self.config.profiles.append(clone)
        self.config.active_profile = name
        self._active_name = name
        self._load_profiles()
        self._save_config()

    def _rename_profile(self) -> None:
        current = self.config.profile(self._active_name)
        if current is None:
            return
        name, ok = self._ask_text("重命名配置", "新名称：", current.name)
        name = (name or "").strip()
        if not ok or not name or name == current.name:
            return
        if self.config.profile(name) is not None:
            self._show_error("配置已存在", name)
            return
        current.name = name
        self.config.active_profile = name
        self._active_name = name
        self._load_profiles()
        self._save_config()

    def _delete_profile(self) -> None:
        if len(self.config.profiles) <= 1:
            self._show_error("至少保留一个配置", "无法删除最后一个配置")
            return
        current = self.config.profile(self._active_name)
        if current is None:
            return
        dialog = ConfirmDialog(self, "删除配置", "确定删除配置「%s」？" % current.name,
                                "删除", "取消")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.config.profiles = [item for item in self.config.profiles if item is not current]
        self.config.active_profile = self.config.profiles[0].name
        self._active_name = self.config.active_profile
        self._load_profiles()
        self._save_config()

    # ------------------------------------------------------------ 连接/库表
    def _test_connection(self) -> None:
        profile = self._collect_profile()
        if profile is None:
            return
        if not profile.host or not profile.user:
            self._show_error("请先填写主机与用户名", "")
            return
        self.connect_button.setEnabled(False)
        self.connection_status.set_state("warn", "连接中…")
        worker = PingWorker(profile, self)
        worker.sig_done.connect(self._on_ping_done)
        worker.sig_error.connect(self._on_worker_error)
        worker.finished.connect(lambda: self.connect_button.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_ping_done(self, version: str) -> None:
        self.connection_status.set_state("ok", "已连接 · MySQL %s" % version)
        self.status_label.setText("连接成功，正在加载数据库…")
        self._log("连接成功：MySQL %s" % version)
        self._refresh_databases()

    def _refresh_databases(self) -> None:
        profile = self._collect_profile()
        if profile is None:
            return
        if not profile.host or not profile.user:
            self._show_error("请先填写主机与用户名", "")
            return
        self.refresh_button.setEnabled(False)
        worker = DatabasesWorker(profile, self.system_db_check.isChecked(), self)
        worker.sig_done.connect(self._on_databases_loaded)
        worker.sig_error.connect(self._on_worker_error)
        worker.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_databases_loaded(self, names) -> None:
        profile = self.config.profile(self._active_name)
        selected = set(profile.selected_databases) if profile is not None else set()
        self.database_list.blockSignals(True)
        self.database_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in selected
                               else Qt.CheckState.Unchecked)
            item.setSizeHint(QSize(0, 36))
            self.database_list.addItem(item)
        self.database_list.blockSignals(False)
        self._database_loaded = True
        self._db_tables.clear()
        self._db_loading.clear()
        self._cancel_row_count()
        self._row_count_started.clear()
        self._current_db = None
        self._tables_db = None
        self._log("已加载 %d 个数据库" % len(names))
        if names:
            self._show_database_list()
            self.status_label.setText("已加载 %d 个数据库" % len(names))
        else:
            self._show_database_hint("没有可用数据库")
        self._rebuild_database_tabs()

    def _on_database_checked(self, item: QListWidgetItem) -> None:
        state = "导出" if item.checkState() == Qt.CheckState.Checked else "不导出"
        self._log("数据库 %s：%s" % (item.text(), state))
        self._rebuild_database_tabs()
        self._schedule_next_table_load()

    def _on_database_highlighted(self, current, previous) -> None:
        if current is None:
            return
        db = current.text()
        if db not in self._checked_databases():
            return
        self._activate_database(db)

    # ---------------------------------------------------------- 表数据加载
    def _checked_databases(self) -> list[str]:
        return [self.database_list.item(index).text()
                for index in range(self.database_list.count())
                if self.database_list.item(index).checkState() == Qt.CheckState.Checked]

    def _rebuild_database_tabs(self) -> None:
        checked = self._checked_databases()
        active = self._current_db if self._current_db in checked else (
            checked[0] if checked else None)
        self.database_tabs.blockSignals(True)
        self.database_tabs.clear()
        for db in checked:
            self.database_tabs.addTab(db, db)
        if active is not None:
            self.database_tabs.setCurrentIndex(checked.index(active))
        self.database_tabs.blockSignals(False)
        self.database_tabs.setVisible(bool(checked))
        self.tab_scrollbar.setVisible(False)
        QTimer.singleShot(0, self._sync_tab_scrollbar)
        if active is not None:
            self._ensure_tab_visible(checked.index(active))
        self._activate_database(active)
        self._sync_database_current_row(active)

    def _database_item(self, name: str):
        for row in range(self.database_list.count()):
            item = self.database_list.item(row)
            if item.text() == name:
                return item
        return None

    def _on_tab_close_requested(self, index: int) -> None:
        """关闭 Tab = 左侧取消勾选该库。"""
        name = self.database_tabs.tabText(index)
        # 等 TabBar 的点击信号返回后再重建，避免在信号里清空自己
        QTimer.singleShot(0, lambda: self._uncheck_database(name))

    def _uncheck_database(self, name: str) -> None:
        item = self._database_item(name)
        if item is not None:
            item.setCheckState(Qt.CheckState.Unchecked)

    def _check_database(self, name: str) -> None:
        item = self._database_item(name)
        if item is not None:
            item.setCheckState(Qt.CheckState.Checked)

    def _sync_tab_scrollbar(self) -> None:
        inner = self.database_tabs.horizontalScrollBar()
        self.tab_scrollbar.blockSignals(True)
        self.tab_scrollbar.setRange(inner.minimum(), inner.maximum())
        self.tab_scrollbar.setPageStep(inner.pageStep())
        self.tab_scrollbar.setValue(inner.value())
        self.tab_scrollbar.blockSignals(False)
        visible = inner.maximum() > 0 and self.database_tabs.isVisible()
        self.tab_scrollbar.setVisible(visible)

    def _on_tab_inner_scrolled(self, value: int) -> None:
        if self.tab_scrollbar.value() != value:
            self.tab_scrollbar.blockSignals(True)
            self.tab_scrollbar.setValue(value)
            self.tab_scrollbar.blockSignals(False)

    def _on_tab_scrollbar_scrolled(self, value: int) -> None:
        inner = self.database_tabs.horizontalScrollBar()
        if inner.value() != value:
            inner.setValue(value)

    def _sync_tab_current(self, db: str | None) -> None:
        """左侧点库/代码切换时同步 Tab 高亮与可见位置。"""
        if db is None:
            return
        checked = self._checked_databases()
        if db not in checked or self.database_tabs.count() != len(checked):
            return
        index = checked.index(db)
        if self.database_tabs.currentIndex() != index:
            self.database_tabs.blockSignals(True)
            self.database_tabs.setCurrentIndex(index)
            self.database_tabs.blockSignals(False)
        self._ensure_tab_visible(index)

    def _ensure_tab_visible(self, index: int) -> None:
        tabs = self.database_tabs
        if not (0 <= index < len(tabs.items)):
            return
        item = tabs.items[index]
        bar = tabs.horizontalScrollBar()
        if bar.maximum() <= 0:
            return
        left = item.x()
        right = left + item.width()
        viewport = tabs.viewport().width()
        if left < bar.value():
            bar.setValue(left)
        elif right > bar.value() + viewport:
            bar.setValue(right - viewport)

    def _sync_database_current_row(self, db: str | None) -> None:
        if db is None:
            return
        self.database_list.blockSignals(True)
        for row in range(self.database_list.count()):
            if self.database_list.item(row).text() == db:
                self.database_list.setCurrentRow(row)
                break
        self.database_list.blockSignals(False)

    def _activate_database(self, db: str | None) -> None:
        if db is not None and db not in self._checked_databases():
            db = None
        self._sync_tab_current(db)
        if db == self._current_db:
            if db is not None and db in self._db_tables:
                self._tables = list(self._db_tables[db])
                self._tables_db = db
                self._render_tables()
            return
        self._cancel_row_count()
        self._store_current_db_state()
        self._current_db = db
        self.table_filter.blockSignals(True)
        self.table_filter.clear()
        self.table_filter.blockSignals(False)
        if db is None:
            self._tables = []
            self._tables_db = None
            self.table_list.set_tables([], set())
            self.table_summary.setText("")
            self._show_table_hint("勾选左侧数据库后查看表")
            return
        tables = self._db_tables.get(db)
        if tables is not None:
            self._tables = list(tables)
            self._tables_db = db
            self._render_tables()
        else:
            self._tables = []
            self._tables_db = None
            self.table_summary.setText("加载中…")
            self._show_table_hint("加载中…")
            self._ensure_tables_loaded(db)

    def _tab_clicked(self, index: int) -> None:
        text = ""
        if hasattr(self.database_tabs, "tabText"):
            text = self.database_tabs.tabText(index)
        if not text:
            checked = self._checked_databases()
            if 0 <= index < len(checked):
                text = checked[index]
        if text:
            self._activate_database(text)
            self._sync_database_current_row(text)

    def _on_filter_changed(self, text: str) -> None:
        self.table_list.apply_filter(text)

    def _ensure_tables_loaded(self, db: str) -> None:
        if db in self._db_tables or db in self._db_loading:
            return
        profile = self._collect_profile()
        if profile is None:
            return
        if not self._db_loading:
            self._loading_started = time.time()
            self._loading_timer.start()
        self._db_loading.add(db)
        worker = TablesWorker(profile, db, self)
        worker.sig_done.connect(lambda tables, db=db: self._on_tables_loaded(db, tables))
        worker.sig_error.connect(
            lambda message, detail, db=db: self._on_tables_load_failed(db, message, detail))
        self._worker = worker
        worker.start()

    def _on_loading_tick(self) -> None:
        if not self._db_loading:
            self._loading_timer.stop()
            self._loading_started = 0.0
            return
        if (self._current_db in self._db_loading
                and self.table_stack.currentWidget() is self.table_hint):
            elapsed = time.time() - self._loading_started
            self.table_hint.setText("加载中…（%.1f 秒）" % elapsed)

    def _schedule_next_table_load(self) -> None:
        if self._db_loading:
            return
        for db in self._checked_databases():
            if db not in self._db_tables:
                self._ensure_tables_loaded(db)
                return

    def _on_tables_loaded(self, db: str, tables) -> None:
        self._db_loading.discard(db)
        if not self._db_loading:
            self._loading_timer.stop()
            self._loading_started = 0.0
        self._db_tables[db] = list(tables)
        if db == self._current_db:
            self._tables = list(tables)
            self._tables_db = db
            self._render_tables()
        self._log("数据库 %s：%d 个表/视图" % (db, len(tables)))
        self._schedule_next_table_load()

    def _on_tables_load_failed(self, db: str, message: str, detail: str) -> None:
        self._db_loading.discard(db)
        if not self._db_loading:
            self._loading_timer.stop()
            self._loading_started = 0.0
        self._db_tables[db] = []
        if db == self._current_db:
            self._tables = []
            self._tables_db = db
            self.table_list.set_tables([], set())
            self.table_summary.setText("")
            self._show_table_hint("加载失败：%s" % message)
        self._log("数据库 %s 表加载失败：%s" % (db, message))
        if detail:
            self._log(detail)
        self._schedule_next_table_load()

    def _render_tables(self) -> None:
        """按当前库的排除配置渲染表清单（正则命中的行锁定为仅结构）。"""
        if self._current_db is None:
            return
        exclude = self._db_excludes.get(self._current_db, ExcludeConfig())
        classified = classify_tables(self._tables, exclude, True)
        reasons = {item.info.name: item.reason for item in classified}
        locked = {item.info.name for item in classified
                  if item.reason.startswith("命中正则")
                  and (item.info.is_view or not item.export_data)}
        excluded = set(exclude.exclude_tables) | locked
        self.table_list.set_tables(self._tables, excluded, reasons, locked=locked)
        self.table_list.apply_filter(self.table_filter.text())
        self._refresh_table_summary()
        self._ensure_row_counts()
        if self._tables:
            self._show_table_list()
        else:
            self._show_table_hint("该库没有表或视图")

    # ------------------------------------------------------ 精确行数统计
    def _ensure_row_counts(self) -> None:
        """当前库有未统计的表时，后台自动 COUNT(*)，不阻塞列表。"""
        if not AUTO_ROW_COUNTS:
            return
        db = self._current_db
        if db is None or db in self._row_count_started:
            return
        names = [item.name for item in self._tables if not item.rows_exact]
        if not names:
            return
        self._row_count_started.add(db)
        self._row_count_db = db
        self.row_count_label.setText("精确行数统计中…")
        worker = RowCountWorker(self._collect_profile(), db, names, self)
        worker.sig_progress.connect(self._on_row_count_progress)
        worker.sig_skipped.connect(self._on_row_count_skipped)
        worker.sig_done.connect(self._on_row_count_done)
        self._row_count_worker = worker
        worker.start()

    def _cancel_row_count(self) -> None:
        worker = self._row_count_worker
        db = self._row_count_db
        self._row_count_worker = None
        self._row_count_db = None
        self.row_count_label.setText("")
        if db is not None:
            self._row_count_started.discard(db)
        if worker is not None:
            worker.cancel()

    def _table_info(self, db: str, name: str):
        for info in self._db_tables.get(db, []):
            if info.name == name:
                return info
        return None

    def _on_row_count_progress(self, db: str, name: str, rows: int,
                               done: int, total: int) -> None:
        if rows >= 0:
            info = self._table_info(db, name)
            if info is not None:
                info.est_rows = rows
                info.rows_exact = True
                info.rows_note = ""
            if db == self._current_db:
                self.table_list.set_row_count(name, rows)
        if db == self._current_db:
            self.row_count_label.setText("精确行数 %d/%d…" % (done, total))

    def _on_row_count_skipped(self, db: str, name: str, reason: str) -> None:
        info = self._table_info(db, name)
        if info is not None:
            info.rows_note = reason
        if db == self._current_db:
            self.table_list.set_row_count_note(name, reason)

    def _on_row_count_done(self, db: str, result) -> None:
        if db == self._current_db:
            self.row_count_label.setText("")
        if self._row_count_db == db:
            self._row_count_worker = None
            self._row_count_db = None
        if result:
            self._log("精确行数统计完成：%s，%d 张" % (db, len(result)))

    def _show_database_hint(self, text: str) -> None:
        self.database_hint.setText(text)
        self.database_stack.setCurrentWidget(self.database_hint)

    def _show_database_list(self) -> None:
        self.database_stack.setCurrentWidget(self.database_list)

    def _show_table_hint(self, text: str) -> None:
        self.table_hint.setText(text)
        self.table_stack.setCurrentWidget(self.table_hint)

    def _show_table_list(self) -> None:
        self.table_stack.setCurrentWidget(self.table_list)

    # ------------------------------------------------------------ 排除规则
    def _store_current_db_state(self) -> None:
        db = self._current_db
        if not db or self._tables_db != db:
            return
        locked = set(self.table_list.locked_names())
        manual = [name for name in self.table_list.excluded_names() if name not in locked]
        existing = self._db_excludes.get(db, ExcludeConfig())
        self._db_excludes[db] = ExcludeConfig(
            exclude_tables=manual,
            exclude_regexes=list(existing.exclude_regexes))

    def _refresh_reasons(self) -> None:
        db = self._current_db
        if not db:
            return
        exclude = self._db_excludes.get(db, ExcludeConfig())
        reasons = {item.info.name: item.reason
                   for item in classify_tables(self._tables, exclude, True)}
        self.table_list.update_reasons(reasons)

    def _refresh_table_summary(self) -> None:
        if not self._tables:
            self.table_summary.setText("")
            return
        exclude = self._db_excludes.get(self._current_db or "", ExcludeConfig())
        classified = classify_tables(self._tables, exclude, True)
        tables = sum(1 for item in classified if not item.info.is_view)
        structure_only = sum(1 for item in classified
                             if not item.info.is_view and not item.export_data)
        views = sum(1 for item in classified
                    if item.info.is_view and item.export_structure)
        self.table_summary.setText(
            "表 %d · 导出 %d · 仅结构 %d · 视图 %d"
            % (tables, tables - structure_only, structure_only, views))

    def _add_excluded_names(self, db: str, names: list[str]) -> None:
        current = self._db_excludes.get(db, ExcludeConfig())
        existing = list(current.exclude_tables)
        lowered = {name.lower() for name in existing}
        for name in names:
            if name.lower() not in lowered:
                existing.append(name)
                lowered.add(name.lower())
        self._db_excludes[db] = ExcludeConfig(
            exclude_tables=existing, exclude_regexes=list(current.exclude_regexes))

    def _exclude_selected(self) -> None:
        db = self._current_db
        if db is None:
            self._show_error("没有选中数据库", "先勾选左侧数据库")
            return
        names = self.table_list.selected_names()
        if not names:
            self._show_error("没有选中行", "先在表清单里选中要排除的行（Ctrl/Shift 可多选）")
            return
        self._add_excluded_names(db, names)
        self._render_tables()
        self.status_label.setText("已排除 %d 个表" % len(names))
        self._log("数据库 %s 排除选中：%s" % (db, "、".join(names)))

    def _batch_exclude(self) -> None:
        checked = self._checked_databases()
        if not checked:
            self._show_error("没有勾选数据库", "先在左侧勾选要导出的库")
            return
        dialog = BatchExcludeDialog(self, len(checked))
        if dialog.exec() != BatchExcludeDialog.Accepted:
            return
        names = dialog.names()
        if not names:
            return
        targets = checked if dialog.apply_all() else (
            [self._current_db] if self._current_db else [])
        for db in targets:
            self._add_excluded_names(db, names)
        if self._current_db is not None:
            self._render_tables()
        self._log("批量排除 %d 个表名（%s）" % (len(names), "、".join(targets)))
        self.status_label.setText("批量排除已应用：%d 个表名" % len(names))

    def _bulk_check(self, mode: str) -> None:
        if mode == "all":
            self.table_list.check_all(True)
        elif mode == "none":
            self.table_list.check_all(False)
        else:
            self.table_list.invert()
        self._store_current_db_state()
        self._refresh_reasons()
        self._refresh_table_summary()

    def _on_table_checked(self, _item) -> None:
        self._store_current_db_state()
        self._refresh_reasons()
        self._refresh_table_summary()

    def _edit_regexes(self) -> None:
        active = self._current_db
        if active is None:
            self._show_error("请先选择数据库", "勾选库并在右侧 Tab 中查看表后再设置正则")
            return
        checked = self._checked_databases()
        self._store_current_db_state()
        current = self._db_excludes.get(active, ExcludeConfig())
        dialog = RegexDialog(self, current.exclude_regexes, len(checked))
        if dialog.exec() != RegexDialog.Accepted:
            return
        targets = checked if dialog.apply_all() and checked else [active]
        for db in targets:
            tables = self._db_excludes.get(db, ExcludeConfig())
            self._db_excludes[db] = ExcludeConfig(
                exclude_tables=list(tables.exclude_tables),
                exclude_regexes=dialog.patterns())
        self._render_tables()
        self._log("正则排除（%s）：%s"
                  % ("、".join(targets), "、".join(dialog.patterns()) or "（空）"))

    # ----------------------------------------------------------------- 导出
    def _browse_outdir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                                     self.outdir_edit.text().strip())
        if directory:
            self.outdir_edit.setText(directory)

    def _build_plans(self, profile: Profile) -> list[DatabasePlan]:
        selected = [self.database_list.item(index).text()
                    for index in range(self.database_list.count())
                    if self.database_list.item(index).checkState() == Qt.CheckState.Checked]
        return build_plan(profile, selected)

    def _preview(self) -> None:
        profile = self._collect_profile()
        if profile is None:
            return
        plans = self._build_plans(profile)
        if not plans:
            self._show_error("没有勾选任何数据库", "请在左侧勾选要导出的库")
            return
        self.preview_button.setEnabled(False)
        snapshot = copy.deepcopy(profile)
        worker = PreviewWorker(snapshot, plans, snapshot.options, self)
        worker.sig_done.connect(self._on_preview_done)
        worker.sig_error.connect(self._on_worker_error)
        worker.finished.connect(lambda: self.preview_button.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_preview_done(self, report) -> None:
        lines = []
        for item in report.databases:
            if item.errors:
                lines.append("%s：失败（%s）" % (item.db, "；".join(item.errors)))
                continue
            data_tables = [c for c in item.classified
                           if not c.info.is_view and c.export_data]
            structure_only = [c for c in item.classified
                              if not c.info.is_view and not c.export_data]
            views = [c for c in item.classified if c.info.is_view and c.export_structure]
            estimated = sum(c.info.est_rows for c in data_tables)
            lines.append("%s：导出表 %d（约 %s 行），仅结构 %d，视图 %d"
                         % (item.db, len(data_tables), format(estimated, ","),
                            len(structure_only), len(views)))
            for classified in structure_only:
                lines.append("    仅结构：%s（%s）"
                             % (classified.info.name, classified.reason))
        text = "\n".join(lines) or "没有可导出的内容"
        self._log("预览（未写文件）：\n" + text)
        TextViewDialog(self, "导出预览（未写文件）", text).exec()

    def _start_export(self) -> None:
        self._cancel_row_count()
        profile = self._collect_profile()
        if profile is None:
            return
        plans = self._build_plans(profile)
        if not plans:
            self._show_error("没有勾选任何数据库", "请在左侧勾选要导出的库")
            return
        outdir = Path(self.outdir_edit.text().strip() or config_mod.default_export_dir())
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._show_error("输出目录不可用", str(exc))
            return
        if not profile.options.filename_timestamp:
            existing = [str(output_path_for(outdir, plan.db, profile.options))
                        for plan in plans]
            existing = [path for path in existing if Path(path).exists()]
            if existing:
                dialog = ConfirmDialog(self, "确认覆盖",
                                       "以下文件已存在，是否覆盖？\n" + "\n".join(existing),
                                       "覆盖", "取消", 640)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
        self._save_config()
        self._current_outdir = outdir
        self._init_log_file(outdir)
        self._log("开始导出：%d 个库 -> %s" % (len(plans), outdir))
        self._set_exporting(True)
        snapshot = copy.deepcopy(profile)
        worker = ExportWorker(snapshot, plans, snapshot.options, outdir, self)
        worker.sig_log.connect(self._log)
        worker.sig_progress.connect(self._on_progress)
        worker.sig_finished.connect(self._on_export_finished)
        worker.sig_error.connect(self._on_export_error)
        worker.finished.connect(lambda: self._set_exporting(False))
        self._worker = worker
        worker.start()

    def _set_exporting(self, exporting: bool) -> None:
        for widget in (self.connect_button, self.refresh_button, self.preview_button,
                       self.export_button, self.select_all_button,
                       self.select_none_button, self.regex_button,
                       self.host_edit, self.port_spin, self.user_edit,
                       self.password_edit, self.outdir_edit, self.browse_button,
                       self.options_button, self.profile_combo,
                       self.config_menu_button, self.system_db_check,
                       self.table_filter, self.exclude_selected_button,
                       self.batch_exclude_button, self.database_tabs):
            widget.setEnabled(not exporting)
        for action in (self.new_button, self.copy_button, self.rename_button,
                       self.delete_button, self.save_button,
                       self.open_config_dir_button):
            action.setEnabled(not exporting)
        self.progress.set_running(exporting)
        self.progress_container.setVisible(exporting)
        if not exporting:
            self._ensure_row_counts()
        if exporting:
            self.progress.set_progress(0, "准备导出…")

    def _on_progress(self, info) -> None:
        if info.db_total:
            within = (info.tables_done / info.tables_total) if info.tables_total else 0.0
            percent = int(((info.db_index + within) / info.db_total) * 100)
        else:
            percent = 0
        text = "%s / %s：%s 行（%.1f 秒）" % (
            info.db, info.table or "…", format(info.rows_in_table, ","), info.elapsed)
        self.progress.set_progress(percent, text)

    def _on_export_finished(self, report) -> None:
        self._log("导出结束：状态=%s，表=%d，行=%s，耗时=%.1f 秒"
                  % (report.status, report.total_tables,
                     format(report.total_rows, ","), report.elapsed))
        self.progress.set_progress(100, "已取消" if report.status == STATUS_CANCELLED else "完成")
        self.status_label.setText("导出结束：%s" % report.status)
        ReportDialog(self, report, self._current_outdir).exec()
        self.progress_container.setVisible(False)
        self._close_log_file()

    def _on_export_error(self, message: str, detail: str) -> None:
        self._log("导出失败：%s" % message)
        if detail:
            self._log(detail)
        self.progress.set_progress(0, "失败")
        ErrorDialog(self, message, detail).exec()
        self.progress_container.setVisible(False)

    def _cancel_export(self) -> None:
        worker = self._worker
        if isinstance(worker, ExportWorker):
            worker.cancel()
            self._log("正在取消，等待当前批次结束…")
            self.progress.cancel_button.setEnabled(False)

    def _on_worker_error(self, message: str, detail: str) -> None:
        self._log("错误：%s" % message)
        self.progress.set_idle()
        self.connection_status.set_state("error", "操作失败")
        ErrorDialog(self, message, detail).exec()
        self.progress_container.setVisible(False)

    # ------------------------------------------------------------ 日志/错误
    def _show_error(self, message: str, hint: str = "") -> None:
        self._log("错误：%s" % message)
        ErrorDialog(self, message, "", hint).exec()

    def _init_log_file(self, outdir: Path) -> None:
        self._close_log_file()
        path = Path(outdir) / ("export-%s.log" % time.strftime("%Y%m%d_%H%M%S"))
        try:
            handler = logging.FileHandler(path, encoding="utf-8")
        except OSError as exc:
            self._log("无法创建日志文件：%s" % exc)
            return
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(handler)
        self._file_handler = handler
        self._log("日志文件：%s" % path)

    def _close_log_file(self) -> None:
        if self._file_handler is not None:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def _log(self, message: str) -> None:
        for line in str(message).splitlines() or [""]:
            self.log_panel.append(line)
            if self._log_dialog is not None and self._log_dialog.isVisible():
                self._log_dialog.append_line(line)
        if self._file_handler is not None:
            self._logger.info(message)

    def _wait_running_threads(self) -> None:
        """等待窗口内仍在运行的线程，避免销毁运行中的 QThread。"""
        threads = list(self.findChildren(QThread))
        if self._worker is not None and self._worker not in threads:
            threads.append(self._worker)
        for thread in threads:
            if thread.isRunning():
                thread.wait(3000)

    def closeEvent(self, event) -> None:
        self._cancel_row_count()
        worker = self._worker
        if worker is not None and worker.isRunning():
            dialog = ConfirmDialog(self, "导出进行中", "导出尚未完成，确定退出吗？",
                                   "退出", "继续导出")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                event.ignore()
                return
            if isinstance(worker, ExportWorker):
                worker.cancel()
            worker.wait(5000)
        self._wait_running_threads()
        self._collect_profile()
        self.config.ui.last_outdir = self.outdir_edit.text().strip()
        try:
            config_mod.save_config(self.config, self.config_path)
        except OSError:
            pass
        self._close_log_file()
        if self._log_dialog is not None:
            self._log_dialog.close()
            self._log_dialog = None
        event.accept()


def run_gui() -> int:
    """启动图形界面事件循环。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    setTheme(Theme.LIGHT)
    setThemeColor("#2563EB")
    window = MainWindow()
    window.show()
    return app.exec()
