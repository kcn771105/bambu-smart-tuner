"""UI 冒烟：走一遍真实保存流程，读日志确认自检与预设隔离。

不弹窗、不覆盖原文件：输出到工程目录旁的 _smoke.3mf。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import rules_engine  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

SRC = _project()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(rules_engine.build_engine(),
                     rules_path=rules_engine.default_rules_path())
    win.resize(1400, 1220)
    win.show()
    win.load_file(str(SRC))
    app.processEvents()

    win.run_optimize(silent=True)
    app.processEvents()

    out = SRC.with_name(SRC.stem + "_smoke.3mf")
    win.ed_out.setText(str(out))
    win.on_save_3mf()
    app.processEvents()

    print(f"输出：{win.last_output}")
    print("--- 日志尾部 ---")
    for line in win.log_view.toPlainText().splitlines()[-10:]:
        print("  " + line)
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
