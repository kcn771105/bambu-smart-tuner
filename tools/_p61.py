import io

p = "tests/test_hotend_safety.py"
s = io.open(p, encoding="utf-8").read()
tail = '''

class TestWallCompat(unittest.TestCase):
    """交替额外墙层与「墙层数 / 确保垂直外壳厚度」的成套要求（Studio 会弹提示那组）。"""

    def setUp(self):
        from core import wall_compat
        self.wc = wall_compat

    def test_turns_off_alternate_wall_when_walls_raised(self):
        ops, warns, notes = self.wc.check(
            {"wall_loops": 6},
            project={"alternate_extra_wall": "1", "wall_loops": "2",
                     "ensure_vertical_shell_thickness": "enabled"})
        self.assertEqual(ops, {"alternate_extra_wall": {"set": False}})
        self.assertTrue(any("交替额外墙" in w for w in warns))
        self.assertTrue(any("已关闭" in n for n in notes))

    def test_sets_partial_shell_when_walls_stay_two(self):
        ops, warns, notes = self.wc.check(
            {"wall_loops": 2},
            project={"alternate_extra_wall": "1", "wall_loops": "2",
                     "ensure_vertical_shell_thickness": "enabled"})
        self.assertEqual(ops, {"ensure_vertical_shell_thickness": {"set": "partial"}})
        self.assertFalse(warns)
        self.assertTrue(any("部分" in n for n in notes))

    def test_noop_when_already_consistent(self):
        ops, _, notes = self.wc.check(
            {"wall_loops": 2},
            project={"alternate_extra_wall": "1",
                     "ensure_vertical_shell_thickness": "partial"})
        self.assertEqual(ops, {})
        self.assertTrue(notes)

    def test_noop_when_feature_off(self):
        for val in ("0", "false", "", None):
            ops, warns, notes = self.wc.check(
                {"wall_loops": 6}, project={"alternate_extra_wall": val})
            self.assertEqual(ops, {})
            self.assertEqual(warns, [])
            self.assertEqual(notes, [])

    def test_schema_has_partial_choice(self):
        from core import schema
        sp = schema.PARAMS["ensure_vertical_shell_thickness"]
        self.assertIn("partial", sp.choices)

    def test_engine_writes_zero_and_warns(self):
        import json
        from core import hardware
        from core.rules_engine import RulesEngine
        from core.threemf import ThreeMfProject
        rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
        eng = RulesEngine(rules)
        prj = ThreeMfProject.load(PROJECT)
        prj.settings["alternate_extra_wall"] = "1"
        hw = hardware.read(prj)
        res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG",
                           nozzle=0.4, mode_key="strength", hardware_info=hw,
                           nozzle_explicit=True)
        self.assertIn("alternate_extra_wall", res.write_values)
        self.assertIn(str(res.write_values["alternate_extra_wall"]).lower(),
                      ("0", "false"))
        self.assertTrue(any("交替额外墙" in w for w in res.warnings))
'''
marker = 'if __name__ == "__main__":'
assert marker in s
s = s.replace(marker, tail.strip("\n") + "\n\n\n" + marker, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("已补 TestWallCompat 6 项")
