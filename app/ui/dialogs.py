"""Fluent 风格对话框：错误详情、导出报告、正则排除、批量排除。

全部基于 QFluentWidgets 的 MessageBoxBase，与主界面视觉一致（圆角、遮罩、主/次按钮）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem
from qfluentwidgets import (BodyLabel, CaptionLabel, CheckBox, LineEdit,
                            MessageBoxBase, PlainTextEdit, PushButton, SpinBox,
                            StrongBodyLabel, TableWidget)

from app.core.classify import validate_regexes
from app.core.models import ExportOptions, ExportReport

_STATUS_TEXT = {"success": "成功", "partial": "部分成功", "cancelled": "已取消",
                "failed": "失败"}


class FluentDialog(MessageBoxBase):
    """带标题与主/次按钮的 Fluent 对话框基类。"""

    def __init__(self, parent, title: str, width: int = 620) -> None:
        super().__init__(parent)
        self.viewLayout.setSpacing(12)
        self.titleLabel = StrongBodyLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        # 按钮不要拉满整行：固定宽度 + 两侧留白，和 Windows/Fluent 对话框一致
        for button in (self.yesButton, self.cancelButton):
            button.setFixedWidth(140)
            self.buttonLayout.setStretch(self.buttonLayout.indexOf(button), 0)
        self.buttonLayout.insertStretch(0, 1)
        self.buttonLayout.addStretch(1)
        self.widget.setMinimumWidth(width)


class ErrorDialog(FluentDialog):
    """错误摘要 + 可复制的详情。"""

    def __init__(self, parent, message: str, detail: str = "", hint: str = "") -> None:
        super().__init__(parent, "出错了", 640)
        title = BodyLabel(message)
        title.setWordWrap(True)
        self.viewLayout.addWidget(title)
        if hint:
            hint_label = CaptionLabel(hint)
            hint_label.setWordWrap(True)
            self.viewLayout.addWidget(hint_label)
        if detail:
            self.detail_text = PlainTextEdit()
            self.detail_text.setPlainText(detail)
            self.detail_text.setReadOnly(True)
            self.detail_text.setMinimumHeight(140)
            self.viewLayout.addWidget(self.detail_text)
        self.cancelButton.hide()


class ReportDialog(FluentDialog):
    """导出结束汇总，可打开输出目录。"""

    def __init__(self, parent, report: ExportReport, outdir: Path | None = None) -> None:
        super().__init__(parent, "导出完成", 780)
        self.report = report
        self.outdir = Path(outdir) if outdir else None

        summary = BodyLabel("状态：%s　表：%d　行：%s　耗时：%.1f 秒"
                            % (_STATUS_TEXT.get(report.status, report.status),
                               report.total_tables, format(report.total_rows, ","),
                               report.elapsed))
        self.viewLayout.addWidget(summary)

        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setRowCount(len(report.databases))
        self.table.setHorizontalHeaderLabels(["数据库", "文件", "表数", "行数", "错误"])
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(220)
        from PySide6.QtWidgets import QHeaderView
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for row, item in enumerate(report.databases):
            self.table.setItem(row, 0, QTableWidgetItem(item.db))
            self.table.setItem(row, 1, QTableWidgetItem(item.path))
            self.table.setItem(row, 2, QTableWidgetItem(str(len(item.tables))))
            self.table.setItem(row, 3, QTableWidgetItem(
                format(sum(t.rows for t in item.tables), ",")))
            self.table.setItem(row, 4, QTableWidgetItem("；".join(item.errors)))
        self.viewLayout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.open_button = PushButton("打开输出目录")
        self.open_button.clicked.connect(self._open_outdir)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        self.viewLayout.addLayout(buttons)

        self.yesButton.setText("关闭")
        self.cancelButton.hide()

    def _open_outdir(self) -> None:
        target = self.outdir
        if target is None and self.report.databases:
            target = Path(self.report.databases[0].path).parent
        if target is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


class RegexDialog(FluentDialog):
    """一行一条正则，实时校验并禁用确定按钮。"""

    def __init__(self, parent, initial: list[str] | None = None,
                 database_count: int = 0) -> None:
        super().__init__(parent, "按正则排除", 600)
        tip = BodyLabel("一行一条正则（大小写不敏感，匹配表名/视图名）：")
        tip.setWordWrap(True)
        self.viewLayout.addWidget(tip)
        self.editor = PlainTextEdit()
        self.editor.setPlainText("\n".join(initial or []))
        self.editor.setMinimumHeight(150)
        self.viewLayout.addWidget(self.editor)
        self.hint = CaptionLabel("")
        self.hint.setWordWrap(True)
        self.viewLayout.addWidget(self.hint)
        self.apply_all_check = CheckBox("应用到所有已勾选的库"
                                        + ("（%d 个）" % database_count if database_count else ""))
        self.apply_all_check.setChecked(False)
        self.viewLayout.addWidget(self.apply_all_check)

        self.ok_button = self.yesButton
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.editor.textChanged.connect(self._validate)
        self._validate()

    def patterns(self) -> list[str]:
        return [line.strip() for line in self.editor.toPlainText().splitlines() if line.strip()]

    def apply_all(self) -> bool:
        return self.apply_all_check.isChecked()

    def _validate(self) -> None:
        error = validate_regexes(self.patterns())
        self.hint.setText(error or "正则校验通过")
        color = "#DC2626" if error else "#059669"
        self.hint.setTextColor(color, color)
        self.ok_button.setEnabled(error is None)


class BatchExcludeDialog(FluentDialog):
    """按表名批量排除（每行一个或用逗号分隔）。"""

    def __init__(self, parent, database_count: int = 0) -> None:
        super().__init__(parent, "批量排除表", 600)
        tip = BodyLabel("输入要排除的表名（每行一个，也可用逗号分隔）；"
                        "命中的表只保留建表语句，不导出数据。")
        tip.setWordWrap(True)
        self.viewLayout.addWidget(tip)
        self.editor = PlainTextEdit()
        self.editor.setPlaceholderText("例如：\nsys_oper_log\nsys_logininfor\ndev_collector_data")
        self.editor.setMinimumHeight(150)
        self.viewLayout.addWidget(self.editor)
        self.apply_all_check = CheckBox("应用到所有已勾选的库"
                                        + ("（%d 个）" % database_count if database_count else ""))
        self.apply_all_check.setChecked(True)
        self.viewLayout.addWidget(self.apply_all_check)
        self.hint = CaptionLabel("")
        self.viewLayout.addWidget(self.hint)

        self.ok_button = self.yesButton
        self.yesButton.setText("排除")
        self.cancelButton.setText("取消")
        self.editor.textChanged.connect(self._validate)
        self._validate()

    def names(self) -> list[str]:
        import re as _re

        raw = self.editor.toPlainText().replace("\n", ",")
        return [name for name in (part.strip() for part in _re.split(r"[,，;；]", raw)) if name]

    def apply_all(self) -> bool:
        return self.apply_all_check.isChecked()

    def _validate(self) -> None:
        names = self.names()
        self.hint.setText("将排除 %d 个表名" % len(names) if names
                          else "请输入至少一个表名")
        self.ok_button.setEnabled(bool(names))


class InfoDialog(FluentDialog):
    """短信息的 Fluent 提示框（关于等）。"""

    def __init__(self, parent, title: str, message: str) -> None:
        super().__init__(parent, title, 560)
        label = BodyLabel(message)
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()


class ConfirmDialog(FluentDialog):
    """确认框：主按钮为确认动作，次按钮取消。"""

    def __init__(self, parent, title: str, message: str,
                 yes_text: str = "确定", cancel_text: str = "取消",
                 width: int = 600) -> None:
        super().__init__(parent, title, width)
        label = BodyLabel(message)
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)
        self.yesButton.setText(yes_text)
        self.cancelButton.setText(cancel_text)


class TextViewDialog(FluentDialog):
    """只读长文本对话框（导出预览等），支持复制。"""

    def __init__(self, parent, title: str, text: str, width: int = 720) -> None:
        super().__init__(parent, title, width)
        self.editor = PlainTextEdit()
        self.editor.setPlainText(text)
        self.editor.setReadOnly(True)
        self.editor.setMinimumSize(660, 380)
        self.viewLayout.addWidget(self.editor)
        row = QHBoxLayout()
        self.copy_button = PushButton("复制")
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        self.viewLayout.addLayout(row)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()

    def content(self) -> str:
        return self.editor.toPlainText()

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.editor.toPlainText())


class LogDialog(FluentDialog):
    """独立运行日志窗口：不再内联展开挤压主界面布局。"""

    def __init__(self, parent) -> None:
        super().__init__(parent, "运行日志", 760)
        self.editor = PlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setMinimumSize(700, 420)
        self.viewLayout.addWidget(self.editor)
        row = QHBoxLayout()
        self.copy_button = PushButton("复制")
        self.copy_button.clicked.connect(self._copy)
        self.clear_button = PushButton("清空")
        self.clear_button.clicked.connect(self.editor.clear)
        row.addWidget(self.copy_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        self.viewLayout.addLayout(row)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def append_line(self, line: str) -> None:
        self.editor.appendPlainText(line)

    def content(self) -> str:
        return self.editor.toPlainText()

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.editor.toPlainText())


class InputDialog(FluentDialog):
    """单行文本输入（新建/复制/重命名配置）。"""

    def __init__(self, parent, title: str, label: str, text: str = "") -> None:
        super().__init__(parent, title, 520)
        tip = BodyLabel(label)
        self.viewLayout.addWidget(tip)
        self.edit = LineEdit()
        self.edit.setText(text)
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self._on_return)
        self.viewLayout.addWidget(self.edit)
        self.hint = CaptionLabel("")
        self.viewLayout.addWidget(self.hint)
        self.ok_button = self.yesButton
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.edit.textChanged.connect(self._validate)
        self._validate()
        self.edit.setFocus()

    def value(self) -> str:
        return self.edit.text().strip()

    def _validate(self) -> None:
        ok = bool(self.value())
        self.hint.setText("" if ok else "名称不能为空")
        self.ok_button.setEnabled(ok)

    def _on_return(self) -> None:
        if self.ok_button.isEnabled():
            self.accept()


class OptionsDialog(FluentDialog):
    """导出设置：时间戳、DROP、编码与批量大小。"""

    def __init__(self, parent, options: ExportOptions) -> None:
        super().__init__(parent, "导出设置", 560)
        tip = CaptionLabel("修改导出 SQL 的文件名与内容选项。")
        tip.setWordWrap(True)
        self.viewLayout.addWidget(tip)
        self.timestamp_check = CheckBox("文件名带时间戳")
        self.timestamp_check.setChecked(options.filename_timestamp)
        self.viewLayout.addWidget(self.timestamp_check)
        self.no_drop_check = CheckBox("不输出 DROP 语句")
        self.no_drop_check.setChecked(not options.drop_before_create)
        self.viewLayout.addWidget(self.no_drop_check)
        self.escape_unicode_check = CheckBox("中文转十六进制")
        self.escape_unicode_check.setChecked(options.escape_unicode)
        self.viewLayout.addWidget(self.escape_unicode_check)
        row = QHBoxLayout()
        row.addWidget(CaptionLabel("每批行数"))
        self.batch_spin = SpinBox()
        self.batch_spin.setRange(1, 100000)
        self.batch_spin.setValue(options.batch_size)
        self.batch_spin.setFixedWidth(140)
        row.addWidget(self.batch_spin)
        row.addStretch(1)
        self.viewLayout.addLayout(row)
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def options(self) -> ExportOptions:
        return ExportOptions(
            escape_unicode=self.escape_unicode_check.isChecked(),
            drop_before_create=not self.no_drop_check.isChecked(),
            include_views=True,
            batch_size=int(self.batch_spin.value()),
            filename_timestamp=self.timestamp_check.isChecked(),
        )
