# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 EXE。

打包命令（在本文件所在目录执行）：
    pyinstaller BambuSmartTuner.spec --noconfirm

产物：dist/BambuSmartTuner.exe
规则库、图标会被打进 EXE；同时会在 dist 下放一份 rules/BambuRules.json 便于用户直接改。
"""

from pathlib import Path

import PyInstaller.__main__  # noqa: F401  （仅用于类型提示，实际由命令行调用）
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()          # noqa: F821  PyInstaller 注入
ASSETS = ROOT / "assets"
RULES = ROOT / "rules"

datas = [
    (str(RULES / "BambuRules.json"), "rules"),
    # Studio 参数位置对照表（「改了我找不到」用）
    (str(ROOT / "data" / "studio_ui.json"), "data"),
    (str(ASSETS / "app.png"), "assets"),
    # 投喂作者的收款码
    (str(ASSETS / "donate.png"), "assets"),
]
if (ASSETS / "app.ico").exists():
    datas.append((str(ASSETS / "app.ico"), "assets"))

# 排除用不到的大模块，明显减小体积
excludes = [
    "tkinter", "unittest", "pydoc", "doctest", "email", "http", "xmlrpc",
    "pdb", "test", "lib2to3", "distutils", "setuptools", "pip",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtRemoteObjects",
    "PyQt5", "PyQt6", "numpy", "pandas", "matplotlib", "PIL",
]

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("core") + collect_submodules("ui"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BambuSmartTuner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                       # 双击不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "app.ico") if (ASSETS / "app.ico").exists() else None,
)
