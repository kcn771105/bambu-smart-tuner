"""UI 层冒烟：在下拉里把喷嘴改成 0.2，确认优化结果的流量上限跟着变，并截图留证。

跑法（必须有窗口平台，离屏缺中文字体）：
    python tools/smoke_ui_nozzle.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import rules_engine  # noqa: E402
from ui import style  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

PROJ = str(_project())
SHOT_DIR = ROOT / "shots"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    style.apply_theme(app)
    engine = rules_engine.build_engine()
    win = MainWindow(engine, rules_path=rules_engine.default_rules_path())
    win.resize(1400, 1220)
    win.show()
    win.load_file(PROJ)
    app.processEvents()

    SHOT_DIR.mkdir(exist_ok=True)
    for nozzle in (0.4, 0.2):
        idx = win.cmb_nozzle.findData(nozzle)
        assert idx >= 0, f"下拉里没有 {nozzle}"
        win.cmb_nozzle.setCurrentIndex(idx)
        win.run_optimize(silent=True)
        app.processEvents()
        res = win.result
        print(f"  下拉选 {nozzle:g} mm → 采用流量上限 "
              f"{res.flow_limit if res.flow_limit else 0:g} mm³/s ｜ "
              f"内壁 {res.values.get('inner_wall_speed'):g} ｜ "
              f"层高 {res.values.get('layer_height'):g} ｜ "
              f"写入 {res.changed_count} 项")
        out = SHOT_DIR / f"ui_nozzle_{nozzle:g}mm.png"
        win.grab().save(str(out))
        print("     截图：", out)

    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
