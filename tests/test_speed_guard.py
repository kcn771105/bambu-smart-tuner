"""「打一个盒子降速严重」的回归测试。

三条根因，各一条测试：
    1. 薄壁误判：`thickness_index`（S/V^(2/3)）对实心平板同样很大，
       160×120×8 的盒子算出 15 > 9.5，被贴上「薄壁/镂空」，吃到一串降速规则。
    2. 重复扣分：形状层把首层速度 ×0.85、几何层又按同一个理由再乘一次，
       50 mm/s 被叠成 36 mm/s。
    3. 静默降速：降了但没人说为什么，用户只能去参数表里猜。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import brief, detector, hardware, model_analysis, rules_engine
from core.threemf import ThreeMfProject

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules" / "BambuRules.json"
PLATE = ROOT / "samples" / "shape_plate_flat.3mf"      # 160×120×8 实心平板（盒子类）


def _optimize(path: Path, mode: str = "balanced"):
    eng = rules_engine.build_engine(str(RULES))
    proj = ThreeMfProject.load(str(path))
    det = detector.detect(proj, eng.rules)
    prof = model_analysis.analyse(proj)
    res = eng.optimize(
        proj.settings,
        printer_key=det.printer_key,
        filament_key=det.filament_key,
        nozzle=det.nozzle,
        mode_key=mode,
        model_profile=prof,
        hardware_info=hardware.read(proj),
    )
    return eng, proj, prof, res


def _rows(res) -> dict:
    return {r.key: r for r in res.rows}


class TestThinWallNotMisjudged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prof = model_analysis.analyse(ThreeMfProject.load(str(PLATE)))

    def test_solid_box_is_not_tagged_thin(self):
        """实心平板不该被贴「薄壁/镂空」。"""
        self.assertNotIn("薄壁/镂空", self.prof.tags())

    def test_solid_box_wall_is_thick(self):
        """160×120×8 的平均壁厚 2V/S ≈ 7.2 mm，离 1.8 很远。"""
        obj = self.prof.objects[0]
        self.assertGreater(obj.wall_thickness, 1.8)
        self.assertGreater(obj.fill_ratio, 0.6)

    def test_thickness_index_still_reports_flatness(self):
        """thickness_index 本身没错，它是「扁平度」不是「薄壁度」，别拿它判薄壁。"""
        self.assertGreater(self.prof.thickness_index, 9.5)


class TestNoDoubleReduction(unittest.TestCase):
    """同一个键不能因为「同一个理由」被两层各乘一次。"""

    @classmethod
    def setUpClass(cls):
        cls.eng, cls.proj, cls.prof, cls.res = _optimize(PLATE)
        cls.rows = _rows(cls.res)

    def test_initial_layer_speed_only_cut_once(self):
        """形状层 ×0.85 之后，几何层不得再叠（50 → 42，不是 50 → 36）。"""
        row = self.rows.get("initial_layer_speed")
        if row is None or not row.changed:
            self.skipTest("该工程首层速度未改动")
        old = float(row.old_display.split()[0])
        new = float(row.new_display.split()[0])
        self.assertGreaterEqual(new / old, 0.80,
                                f"首层速度被叠乘到 {new}/{old}，超过单层扣分上限")

    def test_initial_layer_acceleration_not_stacked(self):
        row = self.rows.get("initial_layer_acceleration")
        if row is None or not row.changed:
            self.skipTest("该工程首层加速度未改动")
        old = float(row.old_display.split()[0])
        new = float(row.new_display.split()[0])
        self.assertGreaterEqual(new / old, 0.75)

    def test_shape_keys_recorded(self):
        """形状层改过的键要留痕，几何层才知道该跳过。"""
        self.assertTrue(self.eng._shape_keys, "形状层没有记录改过的键")


class TestSpeedLineExplainsItself(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, _, cls.res = _optimize(PLATE)
        cls.line = brief._speed_sentence(cls.res)

    def test_speed_line_exists(self):
        self.assertTrue(self.line.startswith("速度："))

    def test_speed_line_has_before_and_after(self):
        self.assertIn("→", self.line)

    def test_flow_cap_is_explained(self):
        """被体积流量上限压住时要写出来，不能让人以为是随便降的。"""
        hit = any("体积流量" in str(r.reason) for r in self.res.rows)
        if not hit:
            self.skipTest("该工程没有触发体积流量上限")
        self.assertIn("体积流量上限", self.line)

    def test_speed_line_in_card(self):
        card = brief.build(self.res, thermal_rows=getattr(self.res, "thermal_rows", None))
        self.assertTrue(any(x.startswith("速度：") for x in card))


class TestPlateLabelsAreChinese(unittest.TestCase):
    """打印板下拉要显示中文，但写进工程的必须还是 Studio 认的英文板型串。"""

    def test_every_plate_has_chinese_label(self):
        from core import thermal
        for label, key in thermal.plate_options():
            self.assertNotEqual(label, key, f"{key} 没有中文名")
            self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in label),
                            f"{key} 的中文名里没有汉字：{label}")

    def test_value_stays_english(self):
        from core import thermal
        keys = [k for _, k in thermal.plate_options()]
        self.assertIn("Supertack Plate", keys)
        self.assertIn("Textured PEI Plate", keys)

    def test_label_lookup_tolerates_raw_settings(self):
        from core import thermal
        self.assertEqual(thermal.plate_label("Textured PEI Plate"), "纹理 PEI 板")
        self.assertIn("超粘", thermal.plate_label("Supertack"))
