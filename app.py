"""Bambu Smart Tuner 入口。

直接运行：
    python app.py
    python app.py path\\to\\工程.3mf      # 启动即加载

打包后：双击 exe 即可。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_NAME = "Bambu Smart Tuner"
APP_VERSION = "1.0.0"


def _fatal(title: str, detail: str) -> None:
    """启动阶段出错时也要让用户看到原因（打包后没有控制台）。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, detail)
    except Exception:
        print(detail, file=sys.stderr)


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Bambu Smart Tuner")

    from ui import icon as app_icon
    from ui import style
    style.apply_theme(app)
    app_icon.apply(app)          # 窗口与任务栏图标（exe 文件图标由 spec 里 icon= 负责）

    from core import rules_engine
    try:
        engine = rules_engine.build_engine()
    except Exception:
        _fatal("规则库加载失败",
               "rules/BambuRules.json 读不到或格式不对：\n\n" + traceback.format_exc())
        return 2

    from ui.main_window import MainWindow
    win = MainWindow(engine, rules_path=rules_engine.default_rules_path())
    win.show()

    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            win.load_file(p)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
