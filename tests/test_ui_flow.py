"""界面级回归测试：把用户报的「选机型后 3mf 不对应 / 参数变回默认 / 界面串行」这几条钉死。

用 offscreen 平台跑，不弹窗；所有保存都落到临时目录。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core import rules_engine, thermal  # noqa: E402
from core.threemf import ThreeMfProject  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

RULES = str(ROOT / "rules" / "BambuRules.json")
PROJ = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

_app = QApplication.instance() or QApplication([])

# 任何弹窗都不要真的弹（offscreen 下也不会显示，但会阻塞）
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def _first(val, default=0.0) -> float:
    """工程里的值是 JSON 文本（如 '["0.4"]'），取第一个数。"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    txt = str(val).strip()
    try:
        data = json.loads(txt)
    except Exception:
        return float(txt.rstrip("mm").strip() or default)
    if isinstance(data, list):
        data = data[0] if data else default
    try:
        return float(data)
    except Exception:
        return default


PLATE_KEY = {
    "Supertack Plate": "supertack_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Smooth PEI Plate": "textured_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "Cool Plate": "cool_plate_temp",
}


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path(PROJ).exists():
            raise unittest.SkipTest("样本工程不在本机")
        cls.engine = rules_engine.build_engine(RULES)

    def make_window(self):
        win = MainWindow(self.engine, rules_path=RULES)
        win.resize(1500, 980)
        win.show()
        _app.processEvents()
        win.load_file(PROJ)
        _app.processEvents()
        win.run_optimize(silent=True)
        _app.processEvents()
        self.addCleanup(win.close)
        return win

    def save_to(self, win, name="out.3mf") -> Path:
        d = Path(tempfile.mkdtemp(prefix="bst_ui_"))
        target = d / name
        win.ed_out.setText(str(target))
        win.on_save_3mf()
        _app.processEvents()
        return Path(win.last_output)


class TestMachineIdenticalToChoice(_Base):
    def test_manual_printer_rewrites_machine_page(self):
        """手选机型后保存的 3mf，机器页必须是这个机型（用户 bug 2/3）。"""
        win = self.make_window()
        idx = win.cmb_printer.findData("P1S")
        self.assertGreaterEqual(idx, 0)
        win.cmb_printer.setCurrentIndex(idx)
        _app.processEvents()
        win.run_optimize(silent=True)

        out = self.save_to(win)
        proj = ThreeMfProject.load(out)
        label = win.cmb_printer.currentText()
        self.assertEqual(proj.settings.get("printer_model"), label)
        self.assertTrue(str(proj.settings.get("printer_settings_id", "")).startswith(label))

    def test_nozzle_follows_choice_in_machine_page(self):
        win = self.make_window()
        idx = win.cmb_nozzle.findData(0.6)
        win.cmb_nozzle.setCurrentIndex(idx)
        _app.processEvents()
        win.run_optimize(silent=True)
        out = self.save_to(win)
        proj = ThreeMfProject.load(out)
        self.assertAlmostEqual(_first(proj.settings.get("nozzle_diameter")), 0.6, places=2)


class TestValuesSurviveReopen(_Base):
    def test_optimized_values_are_in_file_not_defaults(self):
        """保存后再打开，写进去的就是优化后的值，不能退回默认（用户 bug 3）。"""
        win = self.make_window()
        wanted = dict(win.result.write_values)
        self.assertTrue(wanted)
        out = self.save_to(win)
        proj = ThreeMfProject.load(out)
        bad = []
        for key, val in wanted.items():
            got = proj.settings.get(key)
            if str(got).strip() != str(val).strip() and float(str(got).replace("mm", "") or 0) != float(val):
                bad.append((key, val, got))
        self.assertEqual(bad[:5], [])

    def test_process_diff_slots_declared(self):
        win = self.make_window()
        win.run_optimize(silent=True)
        out = self.save_to(win)
        proj = ThreeMfProject.load(out)
        slots = proj.settings.get("different_settings_to_system")
        if isinstance(slots, str):
            slots = json.loads(slots)
        self.assertIsInstance(slots, list)
        self.assertGreaterEqual(len(slots), 3)
        self.assertTrue(str(slots[0]).strip(), "工艺槽没声明，Studio 会按预设盖回默认值")


class TestBedFollowsProject(_Base):
    def test_default_is_follow_project(self):
        win = MainWindow(self.engine, rules_path=RULES)
        self.addCleanup(win.close)
        self.assertIn("跟随工程", win.cmb_bed.itemText(0))
        self.assertFalse(win.cmb_bed.itemData(0))
        self.assertEqual(win._current_bed(), "")

    def test_after_load_bed_follows_project_value(self):
        win = self.make_window()
        self.assertEqual(win._current_bed(), thermal.bed_type_of(win.original_settings))

    def test_plate_temp_key_matches_projects_plate(self):
        win = self.make_window()
        bed = thermal.bed_type_of(win.original_settings)
        self.assertIn(PLATE_KEY[bed], win.result.write_values)

    def test_manual_plate_switches_target_key(self):
        win = self.make_window()
        idx = win.cmb_bed.findData("Textured PEI Plate")
        win.cmb_bed.setCurrentIndex(idx)
        _app.processEvents()
        self.assertIn("textured_plate_temp", win.result.write_values)

    def test_first_layer_is_hotter_than_rest(self):
        """首层要比其余层热，否则首层抓不住板。"""
        win = self.make_window()
        win.cmb_bed.setCurrentIndex(win.cmb_bed.findData("Supertack Plate"))
        _app.processEvents()
        vals = win.result.write_values
        rest = _first(vals.get("supertack_plate_temp"))
        init = _first(vals.get("supertack_plate_temp_initial_layer"))
        self.assertGreater(init, rest)


class TestLayoutNotOverlapping(_Base):
    def test_row_controls_do_not_overlap(self):
        """v1.2 首版把新控件塞到已有行上，打印板下拉被「原始值」标签压住。"""
        win = self.make_window()
        row = [win.cmb_bed, win.sp_room, win.sp_fan, win.cmb_ease]
        rects = [(w.geometry().left(), w.geometry().right()) for w in row]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                self.assertLess(rects[i][1], rects[j][0],
                                f"{i} 与 {j} 横向重叠：{rects[i]} / {rects[j]}")
        self.assertNotEqual(win.cmb_bed.geometry().top(), win.lbl_raw.geometry().top(),
                            "「原始值」标签和打印板那一行撞了")

    def test_detail_boxes_live_in_tabs(self):
        win = self.make_window()
        self.assertIs(win.detail_tabs.widget(1), win.obj_box)
        self.assertIs(win.detail_tabs.widget(2), win.deriv_box)
        self.assertIs(win.detail_tabs.widget(3), win.hw_box)

    def test_conclusion_card_is_visible_and_filled(self):
        win = self.make_window()
        self.assertTrue(win.brief_box.isVisible())
        txt = win.lbl_brief.text()
        self.assertIn("结论", txt)
        self.assertGreater(len(txt), 40)


class TestOutputNaming(_Base):
    def test_default_output_is_v2_and_never_overwrites(self):
        win = self.make_window()
        first = win._default_output()
        self.assertIn("_v2_", first.name)
        first.write_text("x", encoding="utf-8")
        second = win._default_output()
        self.assertNotEqual(first, second)
        self.assertNotEqual(Path(PROJ), first)


if __name__ == "__main__":
    unittest.main()


class TestPresetCanBeUndone(_Base):
    """套用方案后再切回「（不套方案）」，参数必须回到你自己的设置。

    用户反馈「方案关了」——当时关掉方案只是不套用了，界面还停在方案里。
    """

    def test_off_restores_previous_mode(self):
        win = self.make_window()
        before = win._current_mode()
        idx = next((i for i in range(win.cmb_preset.count())
                    if "外观优先" in win.cmb_preset.itemText(i)), -1)
        if idx < 0:
            self.skipTest("没有内置『外观优先』方案")
        win.cmb_preset.setCurrentIndex(idx)
        _app.processEvents()
        self.assertNotEqual(win._current_mode(), before, "套用方案后模式没变，测试前提不成立")
        win.cmb_preset.setCurrentIndex(0)
        _app.processEvents()
        self.assertEqual(win._current_mode(), before, "关掉方案后模式没回到原值")

    def test_off_restores_custom_filament_state(self):
        """撤销要能把『自定义耗材』这类开关也一并还原。"""
        win = self.make_window()
        before = win.cmb_custom.currentData()
        idx = next((i for i in range(win.cmb_preset.count())
                    if "冷天不翘边" in win.cmb_preset.itemText(i)), -1)
        if idx < 0:
            self.skipTest("没有内置『冷天不翘边』方案")
        win.cmb_preset.setCurrentIndex(idx)
        _app.processEvents()
        win.cmb_preset.setCurrentIndex(0)
        _app.processEvents()
        self.assertEqual(win.cmb_custom.currentData(), before)

    def test_snapshot_taken_once(self):
        """在方案之间来回切，撤销点始终是『你自己的设置』，不会被中间方案污染。"""
        win = self.make_window()
        original = win._current_mode()
        for text in ("外观优先", "快速出件", "外观优先"):
            i = next((k for k in range(win.cmb_preset.count())
                      if text in win.cmb_preset.itemText(k)), -1)
            if i >= 0:
                win.cmb_preset.setCurrentIndex(i)
                _app.processEvents()
        win.cmb_preset.setCurrentIndex(0)
        _app.processEvents()
        self.assertEqual(win._current_mode(), original)


class TestVerifyTab(_Base):
    """「验证参数是否都进了切片软件」：保存后逐键对照，界面要能看见结果。"""

    def test_save_fills_verify_tree(self):
        win = self.make_window()
        self.save_to(win)
        self.assertGreater(win.verify_tree.topLevelItemCount(), 0, "核对表是空的")
        self.assertIn("写入", win.lbl_verify.text())

    def test_all_rows_match_right_after_save(self):
        """刚保存完，文件里的值必须和表格里显示的一致（不一致就是写入 bug）。"""
        win = self.make_window()
        self.save_to(win)
        bad = []
        for i in range(win.verify_tree.topLevelItemCount()):
            item = win.verify_tree.topLevelItem(i)
            if "不一致" in item.text(3):
                bad.append((item.text(0), item.text(1), item.text(2)))
        self.assertEqual(bad, [], f"写入后核对不一致：{bad}")

    def test_tab_switches_to_verify(self):
        win = self.make_window()
        self.save_to(win)
        self.assertIs(win.detail_tabs.currentWidget(), win.verify_page)

    def test_room_temp_lands_in_plate_and_fan(self):
        """填了室温，热床温度必须真的写进文件（不是只显示在表里）。"""
        win = self.make_window()
        win.sp_room.setValue(8)
        _app.processEvents()
        win.run_optimize(silent=True)
        _app.processEvents()
        out = self.save_to(win)
        from core.threemf import ThreeMfProject
        got = ThreeMfProject.load(str(out)).settings
        key = PLATE_KEY.get(win.cmb_bed.currentData() or "Supertack Plate",
                            "supertack_plate_temp")
        temp = float(str(got.get(key, "0")).replace('"', '').strip("[]"))
        self.assertGreater(temp, 60.0, f"室温 8°C 时热床仍是 {temp}°C，冷天修正没生效")
