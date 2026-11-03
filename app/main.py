"""程序入口：无参数启动 GUI，带参数走 CLI。"""
from __future__ import annotations

import sys
from pathlib import Path

# 支持 `python app/main.py` 直接运行：把项目根加入 sys.path（PyCharm 脚本运行/任意 CWD 都可用）
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args:
        from app.cli import main as cli_main
        return cli_main(args)
    try:
        from app.ui.main_window import run_gui
    except ModuleNotFoundError as exc:
        # 只在真正缺 PySide6 时给安装提示，避免掩盖其它导入错误
        if (exc.name or "").split(".")[0] == "PySide6":
            print("缺少图形界面依赖 PySide6。请在当前 Python 环境执行："
                  "python -m pip install -r requirements.txt")
            return 2
        raise
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
