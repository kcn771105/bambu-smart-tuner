"""熨烫 / 特殊模式 / 耗材页处理方式（v1.2 新增的「用户自己定」三项）。

运行：
    python -m pytest tests/test_choices.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import filament_write, ironing, rules_engine, special, threemf  # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"
PROJ = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


class TestIroning(unittest.TestCase):
    def test_keep_changes_nothing(self):
        plan = ironing.plan(choice="keep")
        self.assertEqual(plan.ops, {})
        self.assertIn("没有改动", plan.note)

    def test_off_turns_ironing_off(self):
        plan = ironing.plan(choice="off")
        self.assertEqual(plan.ops["ironing_type"], "no ironing")
        self.assertEqual(len(plan.ops), 1)

    def test_auto_sets_four_params(self):
        rules = json.loads(RULES.read_text(encoding="utf-8"))
        plan = ironing.plan(choice="top", auto=True, filament_key="PLA",
                            layer_height=0.2, nozzle=0.4, mode_key="balanced",
                            rules=rules)
        self.assertEqual(plan.ops["ironing_type"], "top")
        for key in ("ironing_flow", "ironing_spacing", "ironing_speed",
                    "ironing_pattern", "ironing_inset"):
            self.assertIn(key, plan.ops)
        self.assertGreater(plan.ops["ironing_flow"], 0)
        self.assertGreater(plan.ops["ironing_spacing"], 0)
        self.assertGreater(plan.ops["ironing_speed"], 0)

    def test_manual_only_changes_type(self):
        plan = ironing.plan(choice="solid", auto=False)
        self.assertEqual(set(plan.ops), {"ironing_type"})
        self.assertEqual(plan.ops["ironing_type"], "solid")

    def test_unknown_choice_is_ignored(self):
        plan = ironing.plan(choice="whatever")
        self.assertEqual(plan.ops, {})
        self.assertIn("不认识", plan.note)

    def test_options_cover_five_states(self):
        keys = [k for _label, k in ironing.type_options()]
        self.assertEqual(keys, ["keep", "top", "topmost", "solid", "off"])


class TestSpecialModes(unittest.TestCase):
    def test_options_from_rules(self):
        opts = special.options(json.loads(RULES.read_text(encoding="utf-8")))
        keys = [o["key"] for o in opts]
        self.assertIn("print_sequence", keys)
        self.assertIn("spiral_mode", keys)
        self.assertIn("fuzzy_skin", keys)

    def test_empty_selection_changes_nothing(self):
        for sel in (None, {}, {"spiral_mode": "keep"}):
            plan = special.plan(sel)
            self.assertEqual(plan.ops, {})

    def test_bool_and_enum_values(self):
        plan = special.plan({"spiral_mode": "1", "print_sequence": "by object",
                             "fuzzy_skin": "external"})
        self.assertIs(plan.ops["spiral_mode"], True)
        self.assertEqual(plan.ops["print_sequence"], "by object")
        self.assertEqual(plan.ops["fuzzy_skin"], "external")
        self.assertEqual(plan.picked, 3)
        self.assertTrue(all("手动选择" in r["measured"] for r in plan.rows))

    def test_garbage_value_is_reported_not_written(self):
        plan = special.plan({"spiral_mode": "maybe"})
        self.assertEqual(plan.ops, {})
        self.assertTrue(any("认不出来" in n for n in plan.notes))


class TestFilamentWrite(unittest.TestCase):
    def test_three_modes(self):
        modes = [m for _label, m in filament_write.mode_options()]
        self.assertEqual(modes, ["keep", "file", "new"])

    def test_new_name_is_idempotent(self):
        self.assertEqual(filament_write.new_name("Bambu PLA Basic"), "Bambu PLA Basic 优化")
        self.assertEqual(filament_write.new_name("Bambu PLA Basic 优化"), "Bambu PLA Basic 优化")

    def test_plan_new_writes_one_name_per_slot(self):
        plan = filament_write.plan("new", base_name='["Bambu PETG HF @BBL P2S"]', slots=2)
        self.assertEqual(plan.ops["filament_settings_id"],
                         ["Bambu PETG HF @BBL P2S 优化"] * 2)
        self.assertTrue(plan.notes)

    def test_plan_file_mode_writes_nothing(self):
        self.assertEqual(filament_write.plan("file").ops, {})

    def test_split_by_mode_drops_filament_page(self):
        values = {"layer_height": "0.2", "fan_max_speed": "80",
                  "textured_plate_temp": "70", "wall_loops": "3"}
        scope = {"layer_height": "process", "fan_max_speed": "thermal",
                 "textured_plate_temp": "thermal", "wall_loops": "process"}.get
        kept, dropped = filament_write.split_by_mode(values, "keep", scope)
        self.assertEqual(sorted(kept), ["layer_height", "wall_loops"])
        self.assertEqual(sorted(dropped), ["fan_max_speed", "textured_plate_temp"])
        kept2, dropped2 = filament_write.split_by_mode(values, "file", scope)
        self.assertEqual(kept2, values)
        self.assertEqual(dropped2, [])


@unittest.skipUnless(PROJ.exists(), "缺少样例工程")
class TestEngineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = rules_engine.build_engine(str(RULES))
        cls.settings = threemf.ThreeMfProject.load(PROJ).settings

    def _run(self, **kw):
        return self.engine.optimize(
            self.settings, printer_key="P2S", filament_key="PLA", nozzle=0.4,
            mode_key="balanced", **kw)

    def test_ironing_reaches_write_values(self):
        res = self._run(ironing_choice="top")
        self.assertEqual(res.write_values.get("ironing_type"), "top")
        self.assertTrue(res.ironing_rows)
        self.assertIn("熨烫", res.ironing)

    def test_special_modes_reach_write_values(self):
        res = self._run(special_modes={"spiral_mode": "1"})
        self.assertEqual(res.write_values.get("spiral_mode"), "1")
        self.assertTrue(res.special_notes)

    def test_filament_keep_drops_filament_page_keys(self):
        res = self._run(filament_mode="keep", room_temp_c=8.0)
        for key in ("fan_max_speed", "fan_min_speed", "supertack_plate_temp",
                    "textured_plate_temp", "nozzle_temperature"):
            self.assertNotIn(key, res.write_values)
        self.assertEqual(res.filament_mode, "keep")
        self.assertTrue(res.filament_note)

    def test_filament_file_mode_keeps_them(self):
        # 冷天会抬高板温 → 热床键必然被改，file 档下这些键应该出现在写入列表里
        res = self._run(filament_mode="file", room_temp_c=8.0)
        self.assertTrue(any(k in res.write_values for k in
                            ("fan_max_speed", "fan_min_speed", "textured_plate_temp",
                             "supertack_plate_temp")))

    def test_filament_new_mode_sets_note(self):
        res = self._run(filament_mode="new")
        self.assertEqual(res.filament_mode, "new")
        self.assertIn("优化", res.filament_note)


if __name__ == "__main__":
    unittest.main()
