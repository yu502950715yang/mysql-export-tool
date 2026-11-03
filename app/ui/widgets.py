"""可复用界面组件：卡片、状态徽标、空态提示、表清单、进度与日志。

基于 QFluentWidgets 组件库，风格与交互由其统一提供。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout,
                               QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, PlainTextEdit,
                            PrimaryPushButton, ProgressBar, PushButton, SimpleCardWidget,
                            StrongBodyLabel, TabBar, TableWidget, TransparentPushButton)

from app.core.models import TableInfo


class StaticCard(SimpleCardWidget):
    """页面级静态面板：圆角边框、无阴影、无悬停动画。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBorderRadius(10)


class Card(StaticCard):
    """页面级卡片：标题 + 右侧操作区 + 内容区（静态面板）。"""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(6)
        self.title_label = StrongBodyLabel(title) if title else None
        if self.title_label is not None:
            self.header.addWidget(self.title_label)
        self.header.addStretch(1)
        outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)

    def add_header_widget(self, widget) -> None:
        self.header.addWidget(widget)

    def add_widget(self, widget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)


class StatusBadge(CaptionLabel):
    """状态徽标：● 文案 + 状态色。"""

    COLORS = {"idle": "#6B7280", "ok": "#059669", "warn": "#D97706", "error": "#DC2626"}

    def __init__(self, text: str = "未连接", parent=None) -> None:
        super().__init__(parent)
        self.set_state("idle", text)

    def set_state(self, state: str, text: str | None = None) -> None:
        if text is not None:
            self.setText("● " + text)
        self.setProperty("state", state)
        color = self.COLORS.get(state, self.COLORS["idle"])
        self.setTextColor(color, color)


class ScrollableTabBar(TabBar):
    """TabBar 是 QScrollArea，默认滚轮不横向滚动；这里把滚轮映射到横向滚动条。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.Wheel:
            bar = self.horizontalScrollBar()
            if bar.maximum() > 0:
                delta = event.angleDelta().y() or event.angleDelta().x()
                if delta:
                    bar.setValue(bar.value() - delta)
                event.accept()
                return True
        return super().eventFilter(watched, event)


class EmptyHint(BodyLabel):
    """空态提示：居中浅灰说明。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setTextColor("#9CA3AF", "#9CA3AF")


class TableListWidget(QWidget):
    """表/视图清单：勾选=导出；支持点击表头排序（名称/类型/行数/注释/说明）。"""

    COL_CHECK, COL_NAME, COL_KIND, COL_ROWS, COL_COMMENT, COL_REASON = range(6)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tables: list[TableInfo] = []
        self._excluded: set[str] = set()
        self._locked: set[str] = set()
        self._reasons: dict[str, str] = {}
        self._filter = ""
        self._sort_column: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        self.table = TableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["", "名称", "类型", "行数", "注释", "说明"])
        self.table.horizontalHeaderItem(self.COL_ROWS).setToolTip(
            "~ 开头为 InnoDB 估算值；列表加载后自动统计精确行数")
        self.table.setToolTip("勾选=导出该表数据；取消勾选=只保留建表语句（不导出数据）")
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_KIND, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_ROWS, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_COMMENT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_REASON, QHeaderView.ResizeMode.Fixed)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.setColumnWidth(self.COL_CHECK, 40)
        self.table.setColumnWidth(self.COL_KIND, 70)
        self.table.setColumnWidth(self.COL_ROWS, 90)
        self.table.setColumnWidth(self.COL_REASON, 170)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    # ---------------------------------------------------------- 对外接口
    def set_tables(self, tables, excluded, reasons=None, locked=None) -> None:
        """按排除集合初始化勾选状态；locked 中的行（如正则命中）不可勾选。"""
        self._tables = list(tables)
        self._excluded = set(excluded)
        self._locked = set(locked or ())
        self._reasons = dict(reasons or {})
        self._render_rows()
        self.table.horizontalScrollBar().setValue(0)
        self.table.verticalScrollBar().setValue(0)

    def tables(self) -> list[TableInfo]:
        return list(self._tables)

    def locked_names(self) -> list[str]:
        """被规则锁定、不可勾选的行（正则命中等）。"""
        return [item.name for item in self._tables if item.name in self._locked]

    def excluded_names(self) -> list[str]:
        excluded = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_CHECK)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                excluded.append(self._tables[row].name)
        return excluded

    def checked_count(self) -> int:
        return sum(1 for row in range(self.table.rowCount())
                   if self.table.item(row, self.COL_CHECK).checkState()
                   == Qt.CheckState.Checked)

    def check_all(self, checked: bool = True) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for row, info in enumerate(self._tables):
            if info.name in self._locked:
                continue
            self.table.item(row, self.COL_CHECK).setCheckState(state)
        self.table.blockSignals(False)
        self._sync_excluded()

    def invert(self) -> None:
        self.table.blockSignals(True)
        for row, info in enumerate(self._tables):
            if info.name in self._locked:
                continue
            item = self.table.item(row, self.COL_CHECK)
            item.setCheckState(Qt.CheckState.Unchecked
                               if item.checkState() == Qt.CheckState.Checked
                               else Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._sync_excluded()

    def update_reasons(self, reasons) -> None:
        self._reasons.update(reasons)
        if self._sort_column == self.COL_REASON:
            self._render_rows()
            return
        for row, info in enumerate(self._tables):
            self.table.item(row, self.COL_REASON).setText(self._reasons.get(info.name, ""))

    def selected_names(self) -> list[str]:
        """当前多选中的表/视图名。"""
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self._tables[row].name for row in rows]

    def set_row_count(self, name: str, rows: int) -> None:
        """把某行更新为精确行数（不重建表格，保留选择/排序）。"""
        for row, info in enumerate(self._tables):
            if info.name != name:
                continue
            info.est_rows = rows
            info.rows_exact = True
            info.rows_note = ""
            item = self.table.item(row, self.COL_ROWS)
            if item is not None:
                item.setText(format(rows, ","))
                item.setToolTip("精确行数")
            return

    def set_row_count_note(self, name: str, note: str) -> None:
        """标记某行精确统计失败，仍保留估算值。"""
        for row, info in enumerate(self._tables):
            if info.name != name:
                continue
            info.rows_note = note
            item = self.table.item(row, self.COL_ROWS)
            if item is not None:
                item.setToolTip("精确统计失败：%s（当前为估算值）" % note)
            return

    def apply_filter(self, text: str) -> None:
        """按表名子串过滤显示（大小写不敏感）。"""
        self._filter = text
        needle = (text or "").strip().lower()
        for row, info in enumerate(self._tables):
            self.table.setRowHidden(row, bool(needle) and needle not in info.name.lower())

    # ---------------------------------------------------------- 内部实现
    def _on_header_clicked(self, column: int) -> None:
        if column not in (self.COL_NAME, self.COL_KIND, self.COL_ROWS,
                          self.COL_COMMENT, self.COL_REASON):
            return
        if self._sort_column == column:
            self._sort_order = (Qt.SortOrder.DescendingOrder
                                if self._sort_order == Qt.SortOrder.AscendingOrder
                                else Qt.SortOrder.AscendingOrder)
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(column, self._sort_order)
        self._sync_excluded()
        self._render_rows()

    def _sort_key(self, info: TableInfo):
        column = self._sort_column
        if column == self.COL_KIND:
            return (info.is_view, info.name.lower())
        if column == self.COL_ROWS:
            return (info.est_rows, info.name.lower())
        if column == self.COL_COMMENT:
            return (info.comment.lower(), info.name.lower())
        if column == self.COL_REASON:
            return (self._reasons.get(info.name, "").lower(), info.name.lower())
        if column == self.COL_NAME:
            return (info.name.lower(),)
        return (info.is_view, info.name.lower())

    def _render_rows(self) -> None:
        column = self._sort_column
        if column is None:
            self._tables.sort(key=lambda item: (item.is_view, item.name.lower()))
        else:
            self._tables.sort(key=self._sort_key,
                              reverse=self._sort_order == Qt.SortOrder.DescendingOrder)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._tables))
        for row, info in enumerate(self._tables):
            excluded = info.name in self._excluded
            check = QTableWidgetItem()
            if info.name in self._locked:
                check.setFlags(Qt.ItemFlag.ItemIsEnabled)
                check.setCheckState(Qt.CheckState.Unchecked)
                check.setToolTip(self._reasons.get(info.name, "已被规则排除"))
            else:
                check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                check.setCheckState(Qt.CheckState.Unchecked if excluded
                                    else Qt.CheckState.Checked)
            self.table.setItem(row, self.COL_CHECK, check)

            name = QTableWidgetItem(info.name)
            if excluded or info.name in self._locked:
                name.setForeground(QColor("#9CA3AF"))
            self.table.setItem(row, self.COL_NAME, name)

            kind = QTableWidgetItem("视图" if info.is_view else "表")
            kind.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, self.COL_KIND, kind)

            if info.rows_exact:
                rows = QTableWidgetItem(format(info.est_rows, ","))
                rows.setToolTip("精确行数")
            else:
                rows = QTableWidgetItem("~" + format(info.est_rows, ","))
                rows.setToolTip(info.rows_note or "InnoDB 估算值，正在统计精确行数…")
            rows.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, self.COL_ROWS, rows)

            comment = QTableWidgetItem(info.comment)
            comment.setForeground(QColor("#6B7280"))
            comment.setToolTip(info.comment)
            self.table.setItem(row, self.COL_COMMENT, comment)

            reason = QTableWidgetItem(self._reasons.get(info.name, ""))
            reason.setForeground(QColor("#6B7280"))
            reason.setToolTip(self._reasons.get(info.name, ""))
            self.table.setItem(row, self.COL_REASON, reason)
        self.table.blockSignals(False)
        self.apply_filter(self._filter)

    def _sync_excluded(self) -> None:
        excluded = set()
        for row, info in enumerate(self._tables):
            item = self.table.item(row, self.COL_CHECK)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                excluded.add(info.name)
        self._excluded = excluded


class ProgressWidget(QWidget):
    """导出进度：状态文字 + 进度条 + 取消按钮。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.label = CaptionLabel("就绪")
        self.label.setMinimumWidth(300)
        self.bar = ProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.cancel_button = TransparentPushButton("取消", icon=FIF.CANCEL)
        self.cancel_button.setEnabled(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.label)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.cancel_button)

    def set_idle(self) -> None:
        self.label.setText("就绪")
        self.bar.setValue(0)
        self.cancel_button.setEnabled(False)

    def set_progress(self, percent: int, text: str) -> None:
        self.bar.setValue(max(0, min(100, int(percent))))
        self.label.setText(text)

    def set_running(self, running: bool) -> None:
        self.cancel_button.setEnabled(running)


class LogPanel(QWidget):
    """只读日志面板，支持复制与清空。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.text = PlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        self.text.setMinimumHeight(104)
        self.text.setMaximumHeight(148)
        self.copy_button = TransparentPushButton("复制", icon=FIF.COPY)
        self.clear_button = TransparentPushButton("清空", icon=FIF.BROOM)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.text)
        layout.addLayout(buttons)
        self.copy_button.clicked.connect(self._copy)
        self.clear_button.clicked.connect(self.text.clear)

    def append(self, line: str) -> None:
        self.text.appendPlainText(line)

    def content(self) -> str:
        return self.text.toPlainText()

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.content())
