# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_DIR = SPEC_DIR.parent

EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DLogic", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSerialPort", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtWebSockets", "PySide6.QtDBus", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", 
     "PySide6.QtNetwork", "PySide6.QtUiTools",
    # 构建环境（Anaconda）里同时装了 PyQt5；QFluentWidgets 会尝试多绑定导入，
    # 必须排除其它 Qt 绑定，否则 PyInstaller 报「multiple Qt bindings」。
    "PyQt5", "PyQt6", "PySide2", "sip",
    "IPython", "jupyter", "jupyter_core", "notebook", "nbformat", "nbconvert", "sphinx", "docutils", "babel", "pytz", "zmq", "black", "jedi", "yapf", "yapf_third_party", "matplotlib", "pandas", "scipy", "sqlalchemy", "pytest", "_pytest", "pluggy",
    "tkinter", "unittest", "pydoc_data",
]

a = Analysis(
    [str(SPEC_DIR / "entry.py")],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MysqlExportTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(SPEC_DIR / "app.ico"),
    version=str(SPEC_DIR / "version_info.txt"),
)
