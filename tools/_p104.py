import io

p = "tests/test_adhesion_support.py"
s = io.open(p, encoding="utf-8").read()
if "TestSupportSwitch" in s:
    print("已存在")
    raise SystemExit(0)

tail = '''


class TestSupportSwitch(unittest.TestCase):
    """支撑开关：auto / on / off（用户要求「开启支撑需要手动调整」）。"""

    def _run(self, mode_key):
        import json as _json
        from pathlib import Path as _Path

        from core import hardware
        from core.rules_engine import RulesEngine
        from core.threemf import ThreeMfProject

        src = _Path(r"F:\\deep seek\\鱼缸温度计支架\\鱼缸温度计支架.3mf")
        if not src.exists():
            self.skipTest("真实工程不在本机")
        root = _Path(__file__).resolve().parent.parent
        rules = _json.load(io.open(root / "rules" / "BambuRules.json", encoding="utf-8-sig"))
        prj = ThreeMfProject.load(src)
        hw = hardware.read(prj)
        eng = RulesEngine(rules)
        return eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG",
                            nozzle=0.4, mode_key="strength", hardware_info=hw,
                            nozzle_explicit=True, support_mode=mode_key)

    def test_off_writes_no_support_key(self):
        res = self._run("off")
        keys = [k for k in res.write_values if k.startswith(("support_", "enable_support"))]
        self.assertEqual(keys, [])

    def test_auto_warns_to_check_placement(self):
        res = self._run("auto")
        self.assertTrue(any("已自动开启支撑" in w for w in res.warnings))

    def test_on_does_not_warn_about_auto(self):
        res = self._run("on")
        self.assertFalse(any("已自动开启支撑" in w for w in res.warnings))
'''

marker = 'if __name__ == "__main__":'
s = s.replace(marker, tail.strip("\n") + "\n\n\n" + marker, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("已补 TestSupportSwitch 3 项")
