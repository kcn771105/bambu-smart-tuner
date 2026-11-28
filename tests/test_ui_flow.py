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
from tests._sample import PROJ as _SAMPLE  # noqa: E402
PROJ = str(_SAMPLE)

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
    "Smooth PEI Plate": "hot_plate_temp",
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
        """工程里的板本机认识就照它选；不认识就换一块它认识的（板温沿用原值）。"""
        win = self.make_window()
        want = thermal.bed_type_of(win.original_settings)
        allowed = win._studio_plate_filter()
        if allowed is None or want in allowed:
            self.assertEqual(win._current_bed(), want)
        else:
            self.assertIn(win._current_bed(), allowed)
            self.assertIsNotNone(win._bed_keep_temp(),
                                 "换板子时必须记住原板温，否则会按新板基线悄悄改温度")

    def test_plate_temp_key_matches_projects_plate(self):
        win = self.make_window()
        bed = win._current_bed() or thermal.bed_type_of(win.original_settings)
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
        bed = win._current_bed()
        if not bed:                                  # 没有可选项就跳过
            self.skipTest("本机 Studio 板型列表为空")
        win.cmb_bed.setCurrentIndex(win.cmb_bed.findData(bed))
        _app.processEvents()
        vals = win.result.write_values
        key = PLATE_KEY[bed]
        rest = _first(vals.get(key))
        init = _first(vals.get(key + "_initial_layer"))
        self.assertGreater(init, rest)


class TestLayoutNotOverlapping(_Base):
    def test_row_controls_do_not_overlap(self):
        """v1.2 首版把新控件塞到已有行上，打印板下拉被「原始值」标签压住。"""
        win = self.make_window()
        row = [win.cmb_bed, win.ed_room, win.cmb_fan, win.cmb_ease]
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


class TestFanAuto(_Base):
    """风扇强弱：默认「自动」，手动档必须盖掉自动修正（不是叠加）。"""

    def test_default_is_auto(self):
        win = self.make_window()
        self.assertIsNone(win._current_fan_trim(), "默认应该是自动（None）")
        self.assertIn("自动", win.cmb_fan.currentText())

    def _fan_max(self, win) -> float:
        """取引擎算完的 fan_max_speed（写不写进文件都一样能看）。"""
        raw = win.result.write_values.get("fan_max_speed") or win.result.values.get("fan_max_speed")
        try:
            return float(json.loads(raw)[0]) if str(raw).startswith("[") else float(raw)
        except (TypeError, ValueError):
            self.fail(f"取不到 fan_max_speed：{raw!r}")

    def test_manual_zero_overrides_cold_auto(self):
        win = self.make_window()
        win.ed_room.setText("8")
        _app.processEvents()
        win.run_optimize(silent=True)
        auto_max = self._fan_max(win)
        idx = win.cmb_fan.findData(0)
        win.cmb_fan.setCurrentIndex(idx)
        _app.processEvents()
        win.run_optimize(silent=True)
        manual_max = self._fan_max(win)
        self.assertGreater(manual_max, auto_max, "手动 0 档不该还带着冷天 −10")


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
        win.ed_room.setText("8")
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


class TestPlateDowngradeWhenStudioLacksIt(_Base):
    """工程用的板本机 Studio 没有（典型：Supertack + 旧版 Studio）时，
    要换成能用的板，但**板温必须沿用原值**，不能按新板基线偷偷改温度。"""

    def _fake_env(self):
        from core import studio_env
        return studio_env.StudioEnv(
            found=True, root="C:/Program Files/Bambu Studio", version="02.03.00.02",
            plates=("Textured PEI Plate", "Smooth PEI Plate / High Temp Plate",
                    "Engineering Plate", "Cool Plate"),
            machines=("Bambu Lab P2S",))

    def test_downgrades_and_keeps_temp(self):
        win = MainWindow(self.engine, rules_path=RULES)
        self.addCleanup(win.close)
        win._studio_cache = self._fake_env()
        win.resize(1500, 980)
        win.show()
        win.load_file(PROJ)
        self.assertEqual(win._current_bed(), "Textured PEI Plate")
        self.assertEqual(win._bed_keep_temp(), 60.0)
        win.run_optimize(silent=True)
        vals = win.result.write_values
        self.assertIn("textured_plate_temp", vals)
        self.assertEqual(_first(vals["textured_plate_temp"]), 60.0,
                         "换板后板温应保持工程原值 60°C，而不是纹理板的 70°C")

    def test_dropdown_only_lists_known_plates(self):
        win = MainWindow(self.engine, rules_path=RULES)
        self.addCleanup(win.close)
        win._studio_cache = self._fake_env()
        win.resize(1500, 980)
        win.show()
        win.load_file(PROJ)
        keys = [win.cmb_bed.itemData(i) for i in range(win.cmb_bed.count())]
        self.assertNotIn("Supertack Plate", keys)
        self.assertIn("Textured PEI Plate", keys)


class TestBedOptionsFollowMachine(_Base):
    """板子下拉只给 Studio 真有的板型，并且跟着机型过滤。"""

    def _allowed_universe(self, win) -> set:
        allowed = win._studio_plate_filter()
        return set(allowed) if allowed is not None else set(thermal.PLATE_TYPES)

    def test_only_plates_this_studio_knows(self):
        """下拉里既有 Studio 认识的板，也不超过 Studio 的五个板型。"""
        win = self.make_window()
        keys = [win.cmb_bed.itemData(i) for i in range(win.cmb_bed.count())]
        self.assertEqual(keys[0], "", "第一项应该是「跟随工程」")
        self.assertNotIn("Smooth PEI Plate", keys)      # 别名不该出现，光滑 PEI 归高温板
        self.assertLessEqual(len(keys), 6)
        allowed = self._allowed_universe(win)
        for key in keys[1:]:
            self.assertIn(key, allowed, f"{key} 本机 Studio 不认识，不该出现在下拉里")

    def test_machine_filter_hides_unsupported(self):
        win = self.make_window()
        idx = win.cmb_printer.findData("H3C")
        self.assertGreaterEqual(idx, 0)
        win.cmb_printer.setCurrentIndex(idx)
        keys = [win.cmb_bed.itemData(i) for i in range(win.cmb_bed.count())]
        self.assertNotIn("Cool Plate", keys)       # H3C 没有低温板
        self.assertNotIn("High Temp Plate", keys)  # 也没有高温/光滑 PEI

    def test_selection_falls_back_when_machine_changes(self):
        win = self.make_window()
        cool = win.cmb_bed.findData("Cool Plate")
        self.assertGreaterEqual(cool, 0)
        win.cmb_bed.setCurrentIndex(cool)
        idx = win.cmb_printer.findData("H3C")
        win.cmb_printer.setCurrentIndex(idx)
        self.assertEqual(win.cmb_bed.currentData(), "",
                         "所选板被机型排除时应退回「跟随工程」")
