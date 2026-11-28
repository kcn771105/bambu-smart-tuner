"""UI 冒烟：强度档跑一遍，确认「按模型实测尺寸推导」表里出现裙边/支撑行，并截图留证。

跑法（必须有窗口平台，离屏缺中文字体）：
    python tools/smoke_bund.py
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
SHOT = ROOT / "shots" / "ui_brim_support.png"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    style.apply_theme(app)
    engine = rules_engine.build_engine()
    win = MainWindow(engine, rules_path=rules_engine.default_rules_path())
    win.resize(1400, 1230)
    win.show()
    win.load_file(PROJ)
    app.processEvents()

    win.radios["strength"].setChecked(True)
    win.run_optimize(silent=True)
    app.processEvents()

    res = win.result
    hits = [d for d in res.derivations if "裙边" in d["metric"] or "支撑" in d["metric"]]
    print(f"推导行 {len(res.derivations)} 条，其中裙边/支撑 {len(hits)} 条：")
    for d in hits:
        print(f"  {d['metric']}\n    实测：{d['measured']}\n    公式：{d['formula']}\n    结论：{d['conclusion']}")
    print(f"裙边：{res.values.get('brim_width')} mm / 类型 {res.values.get('brim_type')}"
          f" ｜ 支撑线距 {res.values.get('support_base_pattern_spacing')}"
          f" ｜ 顶面间隙 {res.values.get('support_top_z_distance')}"
          f" ｜ 水平距 {res.values.get('support_object_xy_distance')}"
          f" ｜ 形态 {res.values.get('support_type')} / {res.values.get('support_style')}")
    SHOT.parent.mkdir(exist_ok=True)
    win.grab().save(str(SHOT))
    print("截图：", SHOT)
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
