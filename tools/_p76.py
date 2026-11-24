import io

p = "tests/test_hotend_safety.py"
s = io.open(p, encoding="utf-8").read()

tail = '''

class TestVariantSlots(unittest.TestCase):
    """按热端变体分槽的数组参数：必须整槽写入，否则 Studio 切到高流量热端读第 1 槽会「看起来没改」。"""

    RAW = '["200", "500", "500"]'

    def tearDown(self):
        from core import schema
        schema.set_variant_slots(0)

    def test_slot_count_from_variant_list(self):
        self.assertEqual(hotend.slot_count({
            "print_extruder_variant": '["Direct Drive Standard", "Direct Drive High Flow",'
                                      ' "Direct Drive E3D High Flow"]'}), 3)
        self.assertEqual(hotend.slot_count({"print_extruder_variant": '["Direct Drive Standard"]'}), 0)
        self.assertEqual(hotend.slot_count({}), 0)

    def test_fill_all_slots_when_variant_count_matches(self):
        from core import schema
        schema.set_variant_slots(3)
        got = schema.format_value(schema.PARAMS["outer_wall_speed"], 150.0, self.RAW)
        self.assertEqual(json.loads(got), ["150", "150", "150"])

    def test_only_first_slot_without_variant_list(self):
        from core import schema
        schema.set_variant_slots(0)
        got = schema.format_value(schema.PARAMS["outer_wall_speed"], 150.0, self.RAW)
        self.assertEqual(json.loads(got), ["150", "500", "500"])

    def test_scalar_value_untouched(self):
        from core import schema
        schema.set_variant_slots(3)
        self.assertEqual(schema.format_value(schema.PARAMS["layer_height"], 0.24, "0.2"), "0.24")

    def test_engine_writes_every_slot(self):
        import io as _io
        from core import hardware
        eng = rules_engine.RulesEngine(json.load(_io.open("rules/BambuRules.json", encoding="utf-8-sig")))
        prj = threemf.ThreeMfProject.load(PROJECT)
        hw = hardware.read(prj)
        res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                           mode_key="balanced", hardware_info=hw, nozzle_explicit=True)
        raw = res.write_values.get("outer_wall_speed")
        self.assertIsNotNone(raw, "outer_wall_speed 应被写入")
        arr = json.loads(raw)
        self.assertEqual(len(arr), 3, "3 个热端变体槽位都要写")
        self.assertEqual(len(set(arr)), 1, "每个槽位写同一个优化值")
'''
marker = 'if __name__ == "__main__":'
s = s.replace(marker, tail.strip("\n") + "\n\n\n" + marker, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("已补 TestVariantSlots 5 项")
