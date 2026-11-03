"""渲染 Fluent 对话框截图（设计核对用）。

用法：python docs/design/capture_dialogs.py
输出：docs/design/ui-dialogs.png（导出报告 / 正则 / 批量排除 / 错误 四个对话框并排）
      docs/design/ui-log-dialog.png（独立运行日志窗口）
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image
from PySide6.QtWidgets import QApplication, QWidget

from app.core.models import DatabaseResult, ExportReport, TableResult
from app.ui.dialogs import (BatchExcludeDialog, ErrorDialog, InputDialog,
                            LogDialog, OptionsDialog, RegexDialog,
                            ReportDialog)
from qfluentwidgets import Theme, setTheme, setThemeColor

OUT = Path(__file__).resolve().parent / "ui-dialogs.png"
TMP = Path(os.environ.get("TEMP", "."))


def grab(dialog, name: str) -> Image.Image:
    dialog.show()
    for _ in range(4):
        QApplication.processEvents()
    path = TMP / name
    dialog.widget.grab().save(str(path))
    image = Image.open(path).convert("RGB")
    dialog.close()
    return image


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    setTheme(Theme.LIGHT)
    setThemeColor("#2563EB")
    host = QWidget()
    host.resize(1240, 860)
    host.show()
    app.processEvents()

    report = ExportReport(
        status="success",
        elapsed=17.5,
        databases=[
            DatabaseResult(db="demo_shop", path=r"E:\...\demo_shop.sql",
                           tables=[TableResult("t", "table", 508_236)]),
            DatabaseResult(db="demo_shop_system", path=r"E:\...\demo_shop_system.sql",
                           tables=[TableResult("t", "table", 65_598)]),
        ],
    )
    images = [
        grab(ReportDialog(host, report, None), "dlg_report.png"),
        grab(RegexDialog(host, [r".*_log$", "^tmp_.*$"], 2), "dlg_regex.png"),
        grab(BatchExcludeDialog(host, 2), "dlg_batch.png"),
        grab(ErrorDialog(host, "无法连接目标主机/端口", "OperationalError(2003, ...)",
                         "检查网络、防火墙与端口号"), "dlg_error.png"),
    ]
    gap = 18
    width = sum(img.width for img in images) + gap * (len(images) + 1)
    height = max(img.height for img in images) + gap * 2
    canvas = Image.new("RGB", (width, height), (243, 244, 246))
    x = gap
    for img in images:
        canvas.paste(img, (x, gap))
        x += img.width + gap
    canvas.save(OUT)

    log_dialog = LogDialog(host)
    log_dialog.set_text("\n".join([
        "10:21:03 连接成功：MySQL 8.1.0",
        "10:21:04 已加载 32 个数据库",
        "10:21:05 开始导出：2 个库 -> E:/code/mysql-export-data/exports",
        "10:21:18 demo_shop：116 个表，完成 508,236 行",
        "10:21:21 demo_shop_system：34 个表，完成 65,598 行",
        "10:21:21 导出结束：状态=success，表=150，行=573,834，耗时=17.5 秒",
    ]))
    log_image = grab(log_dialog, "dlg_log.png")
    log_path = Path(__file__).resolve().parent / "ui-log-dialog.png"
    log_image.save(log_path)

    input_dialog = InputDialog(host, "复制配置", "新配置名：", "Demo 开发库-副本")
    input_image = grab(input_dialog, "dlg_input.png")
    input_path = Path(__file__).resolve().parent / "ui-input-dialog.png"
    input_image.save(input_path)

    from app.core.models import ExportOptions
    options_dialog = OptionsDialog(host, ExportOptions(filename_timestamp=True, batch_size=1000))
    options_image = grab(options_dialog, "dlg_options.png")
    options_path = Path(__file__).resolve().parent / "ui-options-dialog.png"
    options_image.save(options_path)

    print("saved", OUT, canvas.size)
    print("saved", log_path, log_image.size)
    print("saved", input_path, input_image.size)
    print("saved", options_path, options_image.size)


if __name__ == "__main__":
    main()
