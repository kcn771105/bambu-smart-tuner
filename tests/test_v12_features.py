"""v1.2 新增模块的回归测试。

覆盖用户反馈对应的四块新能力：
    机型同步  : core/machine_sync.py    ← 「选了机型后 3mf 不对应」
    接缝光滑  : core/seam_plan.py       ← 「圆柱体接缝能光滑吗」
    三槽声明  : core/preset_diff.py     ← 「参数有时生效有时不生效」
    热床风速  : core/thermal.py         ← 「不同耗材×板子×室温，天冷会翘边」
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import machine_sync, preset_diff, seam_plan, thermal

RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "BambuRules.json"


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


class FakeObj:
    def __init__(self, size_x: float, size_y: float):
        self.size_x = size_x
        self.size_y = size_y


class FakeProfile:
    """只提供 seam_plan 需要的字段，避免真去解析 3mf。"""

    def __init__(self, circle=0.0, slender=0.0, flatness=1.0, objects=()):
        self.circle_score = circle
        self.slender = slender
        self.flatness = flatness
        self.objects = list(objects)


class TestMachineSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def test_same_printer_does_nothing(self):
        plan = machine_sync.plan(self.rules, "A1", detected_key="A1")
        self.assertEqual(plan.ops, {})
        self.assertFalse(plan.changed)
        self.assertTrue(any("保持原样" in n for n in plan.notes))

    def test_disabled_returns_empty(self):
        plan = machine_sync.plan(self.rules, "P1S", detected_key="A1", enabled=False)
        self.assertEqual(plan.ops, {})

    def test_unknown_printer_warns(self):
        plan = machine_sync.plan(self.rules, "NOPE", detected_key="A1")
        self.assertEqual(plan.ops, {})
        self.assertTrue(any("没有" in w for w in plan.warnings))

    def test_rewrites_machine_page_and_fills_missing_standard_keys(self):
        cur = {"printer_model": "A1", "printer_settings_id": "A1 0.4 nozzle",
               "printable_area": '["0x0","256x0","256x256","0x256"]',
               "printable_height": "256"}
        plan = machine_sync.plan(self.rules, "X1C", nozzle=0.6, detected_key="A1",
                                 current=cur)
        self.assertTrue(plan.changed)
        self.assertIn("printer_model", plan.ops)
        self.assertIn("0.6 nozzle", plan.ops["printer_settings_id"])
        # 工程里没存的标准键也要写，否则 Studio 按旧机型预设补回去
        self.assertIn("machine_max_speed_x", plan.ops)
        self.assertIn("printable_area", plan.ops)
        self.assertTrue(any("原来没有" in n for n in plan.notes))
        self.assertTrue(plan.warnings)  # 换机型要提醒校准

    def test_no_change_when_values_already_match(self):
        cur = {"printer_model": "Bambu Lab P1S",
               "printer_settings_id": "Bambu Lab P1S 0.4 nozzle"}
        plan = machine_sync.plan(self.rules, "P1S", nozzle=0.4, detected_key="A1",
                                 current=cur)
        # 机型标识已经是这台机器 → 不再写
        self.assertNotIn("printer_model", plan.ops)
        self.assertNotIn("printer_settings_id", plan.ops)

    def test_area_points_format(self):
        self.assertEqual(machine_sync._area_points([256, 256, 256]),
                         ["0x0", "256x0", "256x256", "0x256"])
        self.assertEqual(machine_sync._area_points([180.5, 180]),
                         ["0x0", "180.5x0", "180.5x180", "0x180"])


class TestSeamPlan(unittest.TestCase):
    def test_disabled(self):
        p = seam_plan.plan(FakeProfile(circle=1.0), enabled=False)
        self.assertEqual(p.ops, {})

    def test_non_round_non_slender_does_nothing(self):
        p = seam_plan.plan(FakeProfile(circle=0.0, slender=1.2))
        self.assertEqual(p.ops, {})

    def test_round_object_gets_aligned_and_scarf(self):
        p = seam_plan.plan(FakeProfile(circle=1.0, slender=3.0,
                                       objects=[FakeObj(40, 40)]),
                           layer_height=0.2)
        self.assertTrue(p.enabled)
        self.assertEqual(p.ops["seam_position"], "aligned")
        self.assertEqual(p.ops["seam_slope_type"], "external")
        self.assertIs(p.ops["apply_scarf_seam_on_circles"], True)
        self.assertEqual(p.ops["seam_slope_steps"], 3)   # round(0.6/0.2)
        self.assertEqual(p.ops["seam_slope_start_height"], 5.0)  # 明确圆
        self.assertTrue(p.rows)

    def test_tiny_circle_falls_back_to_nearest(self):
        p = seam_plan.plan(FakeProfile(circle=1.0, objects=[FakeObj(10, 10)]))
        self.assertEqual(p.ops, {"seam_position": "nearest"})
        self.assertFalse(any(k.startswith("seam_slope") for k in p.ops))

    def test_slender_gets_aligned_with_scarf(self):
        p = seam_plan.plan(FakeProfile(circle=0.0, slender=3.5,
                                       objects=[FakeObj(30, 30)]))
        self.assertEqual(p.ops["seam_position"], "aligned")
        self.assertEqual(p.ops["seam_slope_start_height"], 10.0)

    def test_skips_keys_already_set(self):
        cur = {"seam_position": "aligned", "seam_slope_gap": "0"}
        p = seam_plan.plan(FakeProfile(circle=1.0, objects=[FakeObj(40, 40)]),
                           current=cur)
        self.assertNotIn("seam_position", p.ops)
        self.assertNotIn("seam_slope_gap", p.ops)
        self.assertIn("seam_slope_type", p.ops)


class TestSplitByScope(unittest.TestCase):
    def test_three_slots(self):
        got = preset_diff.split_by_scope([
            "layer_height",              # process → 槽0
            "fan_min_speed",             # thermal → 耗材槽
            "supertack_plate_temp",      # thermal → 耗材槽
            "pressure_advance",          # filament → 耗材槽
            "printer_model",             # machine 结构性 → 丢弃
            "printable_area",            # machine 结构性 → 丢弃
            "machine_max_speed_x",       # machine 非结构性 → 槽2
        ])
        self.assertEqual(got["process"], ["layer_height"])
        self.assertIn("fan_min_speed", got["filament"])
        self.assertIn("supertack_plate_temp", got["filament"])
        self.assertIn("pressure_advance", got["filament"])
        self.assertEqual(got["machine"], ["machine_max_speed_x"])

    def test_update_settings_array_writes_three_slots(self):
        settings = {"different_settings_to_system": ["", "", ""]}
        out = preset_diff.update_settings_array(
            settings,
            process_keys=["layer_height"],
            filament_keys=["fan_min_speed"],
            printer_keys=["machine_max_speed_x"],
        )
        self.assertEqual(len(out), 3)
        self.assertIn("layer_height", out[0])
        self.assertIn("fan_min_speed", out[1])
        self.assertIn("machine_max_speed_x", out[2])


class TestThermalFanTrim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def _fan(self, **kw) -> dict:
        res = thermal.derive(self.rules, {"curr_bed_type": "Supertack Plate"},
                             filament_key="PLA", **kw)
        # thermal.derive 返回的是 op 字典（{"set": 值}）或裸值，统一取值比较
        out = {}
        for k, v in res.ops.items():
            if isinstance(v, dict):
                v = v.get("set", v.get("max", v.get("min", 0)))
            out[k] = v
        return out

    def test_fan_trim_lowers_speed(self):
        base = self._fan(room_temp_c=25)
        low = self._fan(room_temp_c=25, fan_trim=-10)
        b = float(str(base["fan_min_speed"]).strip())
        l = float(str(low["fan_min_speed"]).strip())
        self.assertLess(l, b)

    def test_fan_trim_clamped_to_0_100(self):
        high = self._fan(room_temp_c=25, fan_trim=200)
        for key in ("fan_min_speed", "fan_max_speed", "overhang_fan_speed"):
            v = float(str(high[key]).strip())
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

    def test_cold_room_extra_trim(self):
        warm = self._fan(room_temp_c=25)
        cold = self._fan(room_temp_c=8)
        self.assertLess(float(str(cold["fan_max_speed"]).strip()),
                        float(str(warm["fan_max_speed"]).strip()))

    def test_fan_auto_is_default_and_manual_overrides_it(self):
        """风扇默认自动（None）；手动给 0 就照标定值来，不再叠加冷天修正。"""
        auto_cold = self._fan(room_temp_c=8)
        manual_0 = self._fan(room_temp_c=8, fan_trim=0)
        self.assertLess(float(str(auto_cold["fan_max_speed"]).strip()),
                        float(str(manual_0["fan_max_speed"]).strip()),
                        "自动档在冷天应比手动 0 更低")

    def test_plate_temp_stops_at_ceiling(self):
        """加温有上限：室温再低也不许把板温顶到 85°C 以上（低温板 45°C）。"""
        ops = thermal.derive(self.rules, {"curr_bed_type": "Supertack Plate"},
                             filament_key="PETG", room_temp_c=-5)
        self.assertLessEqual(float(str(ops.ops["supertack_plate_temp"]["set"])), 85.0)
        cool = thermal.derive(self.rules, {"curr_bed_type": "Cool Plate"},
                              filament_key="PLA", room_temp_c=-5)
        self.assertLessEqual(float(str(cool.ops["cool_plate_temp"]["set"])), 45.0)

    def test_room_note_wording_matches_direction(self):
        """天冷说翘边、天热说粘死；22°C 这种常规区间也要给一句话（以前是空的）。"""
        cold = thermal.derive(self.rules, {"curr_bed_type": "Supertack Plate"},
                              filament_key="PETG", room_temp_c=8)
        hot = thermal.derive(self.rules, {"curr_bed_type": "Supertack Plate"},
                             filament_key="PETG", room_temp_c=30)
        mild = thermal.derive(self.rules, {"curr_bed_type": "Supertack Plate"},
                              filament_key="PETG", room_temp_c=22)
        self.assertIn("天冷", cold.room_note)
        self.assertIn("天热", hot.room_note)
        self.assertIn("常规区间", mild.room_note)

    def test_bed_temp_rises_when_room_is_cold(self):
        warm = self._fan(room_temp_c=25)
        cold = self._fan(room_temp_c=8)
        self.assertEqual(warm["supertack_plate_temp"], 60.0)
        self.assertGreater(cold["supertack_plate_temp"],
                           warm["supertack_plate_temp"])
        # 天冷时首层同样加热更久、风扇更小（防翘边）
        self.assertGreater(cold["supertack_plate_temp_initial_layer"],
                           warm["supertack_plate_temp_initial_layer"])
        self.assertLess(cold["fan_min_speed"], warm["fan_min_speed"])


if __name__ == "__main__":
    unittest.main()
