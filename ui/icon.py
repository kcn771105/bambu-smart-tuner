"""给程序窗口/任务栏加上自己的图标。

原来只有 exe 文件图标（spec 里的 icon=），窗口和任务栏用的是 Qt 默认图标，
钉到任务栏或 Alt+Tab 时看起来像“没做图标”。这里在启动时把 assets/app.png 设进去。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def _asset_path(name: str):
    """exe 同目录 assets → 打包内 _MEIPASS/assets → 源码 assets。"""
    cands = []
    exe_dir = Path(sys.executable).resolve().parent
    cands.append(exe_dir / "assets" / name)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(Path(meipass) / "assets" / name)
    cands.append(Path(__file__).resolve().parent.parent / "assets" / name)
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def apply(app) -> bool:
    """给 QApplication 设图标；成功返回 True。"""
    from PySide6.QtGui import QIcon

    for name in ("app.png", "app.ico"):
        p = _asset_path(name)
        if p is None:
            continue
        ic = QIcon(str(p))
        if not ic.isNull():
            app.setWindowIcon(ic)
            return True
    return False
