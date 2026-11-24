import io

p = "tests/test_adhesion_support.py"
s = io.open(p, encoding="utf-8").read()
if "test_engine_keeps_interface_slower" in s:
    print("已存在")
    raise SystemExit(0)

tail = '''


class TestSupportFlowClamp(unittest.TestCase):
    """流量钳制之后，支撑接触面仍必须比本体慢。"""

    def test_engine_keeps_interface_slower(self):
        import json as _json
        from pathlib import Path as _Path

        from core import hardware
        from core.rules_engine import RulesEngine
        from core.threemf import ThreeMfProject

        root = _Path(__file__).resolve().parent.parent
        src = _Path(r"F:\\deep seek\\鱼缸温度计支架\\鱼缸温度计支架.3mf")
        if not src.exists():
            self.skipTest("真实工程不在本机")
        rules = _json.load(io.open(root / "rules" / "BambuRules.json", encoding="utf-8-sig"))
        prj = ThreeMfProject.load(src)
        hw = hardware.read(prj)
        eng = RulesEngine(rules)
        res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG",
                           nozzle=0.4, mode_key="strength", hardware_info=hw,
                           nozzle_explicit=True)
        body = res.write_values.get("support_speed")
        iface = res.write_values.get("support_interface_speed")
        if not body or not iface:
            self.skipTest("该工程没写支撑速度")
        b = float(_json.loads(body)[0] if isinstance(body, str) and body.startswith("[") else body)
        i = float(_json.loads(iface)[0] if isinstance(iface, str) and iface.startswith("[") else iface)
        self.assertLess(i, b * 0.8, f"接触面 {i} 应明显慢于本体 {b}")
'''

marker = 'if __name__ == "__main__":'
s = s.replace(marker, tail.strip("\n") + "\n\n\n" + marker, 1)
if "\nimport io\n" not in s:
    s = s.replace("import unittest", "import io\nimport unittest", 1)
io.open(p, "w", encoding="utf-8").write(s)
print("已补 TestSupportFlowClamp")
