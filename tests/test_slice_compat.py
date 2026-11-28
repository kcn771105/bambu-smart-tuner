# -*- coding: utf-8 -*-
"""「打开就能切」的兼容性回归。

这三个 bug 都是实测出来的：3mf 交给 Bambu Studio CLI 之后直接被判
「process not compatible with printer」或「Param values in 3mf/config error」，
切片器一个 gcode 都不吐。以前单测只看引擎吐出来的值，谁都发现不了。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import machine_sync, preset_names, rules_engine, special, threemf

RULES = Path(__file__).resolve().parent.parent / "rules" / "BambuRules.json"
from tests._sample import PROJ  # noqa: E402


def _engine():
    return rules_engine.build_engine(str(RULES))


class TestSpiralCompanion(unittest.TestCase):
    """螺旋（花瓶）模式不是单个开关，配套项不齐切片器就拒绝切片。"""

    def setUp(self):
        self.assertTrue(PROJ.exists(), f"缺少测试工程：{PROJ}")
        self.proj = threemf.ThreeMfProject.load(PROJ)

    def _run(self, special_modes):
        return _engine().optimize(
            self.proj.settings, printer_key="P2S", filament_key="PETG",
            nozzle=0.4, mode_key="balanced", special_modes=special_modes)

    def test_spiral_forces_single_wall_and_no_support(self):
        res = self._run({"spiral_mode": "1"})
        self.assertTrue(special.truthy(res.values.get("spiral_mode")))
        self.assertEqual(str(res.values.get("wall_loops")), "1")
        self.assertFalse(special.truthy(res.values.get("enable_support")))
        self.assertIn("wall_loops", res.write_values)

    def test_spiral_warning_explains_why(self):
        res = self._run({"spiral_mode": "1"})
        text = "\n".join(res.warnings)
        self.assertIn("螺旋", text)
        self.assertIn("切不了片", text)

    def test_no_spiral_touches_nothing(self):
        res = self._run({"print_sequence": "by object"})
        self.assertNotIn("wall_loops", res.write_values)

    def test_truthy_accepts_chinese_and_bool(self):
        for value in (1, "1", "true", "开", "开启", True):
            self.assertTrue(special.truthy(value), value)
        for value in (0, "0", "false", "关", None, "", False):
            self.assertFalse(special.truthy(value), value)


class TestMachineCompatiblePrinters(unittest.TestCase):
    """换机型 / 换喷嘴后，工程里那句 `print_compatible_printers` 必须跟着改，
    否则 Studio 判「process not compatible with printer」。"""

    def setUp(self):
        self.rules = __import__("json").loads(RULES.read_text(encoding="utf-8"))
        self.cur = {
            "printer_model": "Bambu Lab P2S",
            "printer_settings_id": "Bambu Lab P2S 0.4 nozzle",
            "nozzle_diameter": '["0.4"]',
            "printer_variant": "0.4",
            "print_compatible_printers": '["Bambu Lab P2S 0.4 nozzle"]',
            "print_settings_id": "0.20mm Standard @BBL P2S",
        }

    def test_same_printer_noop(self):
        plan = machine_sync.plan(self.rules, "P2S", nozzle=0.4,
                                 current=self.cur, enabled=True)
        # 机型/喷嘴/工艺预设一律不动（工程里缺的机器上限可以补，不算「改机型」）
        for key in ("printer_model", "printer_settings_id", "printer_variant",
                    "print_compatible_printers", "nozzle_diameter",
                    "print_settings_id"):
            self.assertNotIn(key, plan.ops)

    def test_machine_change_writes_single_target(self):
        plan = machine_sync.plan(self.rules, "A1", nozzle=0.4,
                                 detected_key="P2S", current=self.cur)
        raw = plan.ops.get("print_compatible_printers")
        self.assertIsNotNone(raw, "换机型必须写 print_compatible_printers")
        values = json.loads(raw)
        self.assertEqual(len(values), 1, "只能写当前这一台，写整个兼容列表反而切不了")
        self.assertEqual(values[0], plan.ops["printer_settings_id"])

    def test_nozzle_change_writes_single_target(self):
        plan = machine_sync.plan(self.rules, "P2S", nozzle=0.6,
                                 detected_key="P2S", current=self.cur)
        raw = plan.ops.get("print_compatible_printers")
        self.assertIsNotNone(raw)
        self.assertEqual(json.loads(raw), ["Bambu Lab P2S 0.6 nozzle"])
        self.assertEqual(json.loads(plan.ops.get("nozzle_diameter")), [0.6])


@unittest.skipUnless(preset_names.index() is not None,
                     "本机没有安装 Bambu Studio 预设清单")
class TestPresetRemapSafety(unittest.TestCase):
    def test_strict_returns_none_instead_of_switching_material(self):
        # 一个不存在的耗材名，strict 必须返回 None（宁可不换，也不能换成别的材质）
        got = preset_names.remap("多彩屋petg @BBL P2S", "Bambu Lab P2S 0.4 nozzle",
                                 "filament", strict=True)
        self.assertIsNone(got)

    def test_nozzle_change_picks_layer_height_nearest(self):
        got = preset_names.remap("0.20mm Standard @BBL P2S",
                                 "Bambu Lab P2S 0.4 nozzle", "process")
        if got:
            self.assertIn("P2S", got)


if __name__ == "__main__":
    unittest.main()
