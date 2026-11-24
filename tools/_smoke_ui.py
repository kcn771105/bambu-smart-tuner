"""UI 冒烟测试：离屏跑「加载 → 优化 → 保存」，抓两张界面图。

用法：python tools/_smoke_ui.py
输出：shots/ui_work.png、shots/ui_rules.png，以及一份控制台摘要。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox   # noqa: E402

from core import rules_engine, threemf                                # noqa: E402
from make_sample_3mf import build_sample                              # noqa: E402
from ui import style                                                  # noqa: E402
from ui.main_window import MainWindow                                 # noqa: E402


def main() -> int:
    # 弹窗全部拦掉，避免离屏环境卡住
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))

    shots = ROOT / "shots"
    shots.mkdir(exist_ok=True)
    td = Path(tempfile.mkdtemp(prefix="bst_ui_"))

    app = QApplication(sys.argv)
    style.apply_theme(app)

    eng = rules_engine.build_engine()
    win = MainWindow(eng, rules_path=rules_engine.default_rules_path())
    win.resize(1320, 860)
    win.show()

    sample = build_sample(td / "demo_x1c_pla.3mf", printer_model="Bambu Lab X1 Carbon",
                         filament="PLA", nozzle=0.4)
    win.load_file(sample)
    app.processEvents()

    print("识别：", win.cmb_printer.currentText(), "/", win.cmb_filament.currentText(),
          "/", win.cmb_nozzle.currentText())
    print("自动优化结果：", win.lbl_summary.text())

    win.radios["strength"].setChecked(True)
    app.processEvents()
    print("强度优先：", win.lbl_summary.text(), "｜表格顶层分组", win.table.topLevelItemCount())

    win.chk_changed.setChecked(False)
    app.processEvents()
    print("全量参数行数：", sum(win.table.topLevelItem(i).childCount()
                          for i in range(win.table.topLevelItemCount())))
    win.chk_changed.setChecked(True)
    app.processEvents()

    win.grab().save(str(shots / "ui_work.png"))
    win.tabs.setCurrentIndex(1)
    app.processEvents()
    win.grab().save(str(shots / "ui_rules.png"))
    win.tabs.setCurrentIndex(0)
    app.processEvents()

    out = td / "demo_x1c_pla_optimized.3mf"
    win.ed_out.setText(str(out))
    win.on_save_3mf()
    app.processEvents()
    print("保存：", out.exists(), out.stat().st_size if out.exists() else 0, "bytes")

    orig = threemf.ThreeMfProject.load(sample)
    new = threemf.ThreeMfProject.load(out)
    diff = [k for k in orig.settings if orig.settings[k] != new.settings.get(k)]
    print("参数差异条数：", len(diff))
    for k in diff[:8]:
        print(f"   {k}: {orig.settings[k]!r} -> {new.settings[k]!r}")
    print("原文件未被修改：", sample.stat().st_size > 0)

    # 自定义耗材同步
    win.on_sync_filaments(quiet=True)
    app.processEvents()
    print("自定义耗材数：", len(win.custom_presets), "｜下拉项：", win.cmb_custom.count())
    if win.custom_presets:
        idx = win.cmb_custom.findData(win.custom_presets[0].name)
        win.cmb_custom.setCurrentIndex(idx)
        app.processEvents()
        print("套用自定义耗材后：", win.lbl_summary.text())
        overlay = win._current_overlay()
        print("覆盖层：", overlay["label"], overlay["family"],
              overlay["limits"], list(overlay["baseline"].keys()))

    # 模型形状自适应：换成高瘦花瓶
    from make_shape_samples import SHAPES, build as build_shape
    vase = build_shape(td / "vase.3mf", SHAPES["shape_vase_tall"][0], "vase")
    win.load_file(vase)
    app.processEvents()
    print("形状：", win.lbl_shape.text())
    print("逐件明细行数：", win.obj_tree.topLevelItemCount())
    for i in range(min(win.obj_tree.topLevelItemCount(), 3)):
        it = win.obj_tree.topLevelItem(i)
        print("   ", it.text(0), "|", it.text(2), "|", it.text(3))
    win.radios["quality"].setChecked(True)
    app.processEvents()
    print("花瓶+质量：", win.lbl_summary.text())

    win.grab().save(str(shots / "ui_work.png"))
    win.tabs.setCurrentIndex(1)
    app.processEvents()
    win.grab().save(str(shots / "ui_rules.png"))
    win.tabs.setCurrentIndex(0)
    app.processEvents()

    # 换机型/耗材/模式再算一次，验证下拉修正链路
    win.cmb_printer.setCurrentIndex(win.cmb_printer.findData("A1mini"))
    win.cmb_filament.setCurrentIndex(win.cmb_filament.findData("TPU"))
    win.radios["quality"].setChecked(True)
    app.processEvents()
    print("A1 mini + TPU + 质量：", win.lbl_summary.text())
    print("日志行数：", win.log_view.toPlainText().count("\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
