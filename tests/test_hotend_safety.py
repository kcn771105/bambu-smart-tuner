"""热端流量类型 + 写入纪律（预设隔离 / 自检 / 自定义档标记）的测试。

对应 m05100 的三条：
    1. 写入 == UI（safety.self_check + verify_written_equals_ui）
    2. 热端流量类型识别 + 手改 + 参与规则
    3. 绝不碰 Bambu Studio 预设
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import hotend, preset_diff, rules_engine, safety, threemf  # noqa: E402

PROJECT = str(Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"))

PROJ = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


def _settings(**kw) -> dict:
    base = {
        "nozzle_volume_type": ["Standard"],
        "default_nozzle_volume_type": ["Standard"],
        "extruder_nozzle_stats": ["Standard#1"],
        "printer_extruder_variant": ["Direct Drive Standard", "Direct Drive High Flow"],
        "print_extruder_variant": ["Direct Drive Standard"],
        "nozzle_volume": ["110", "110", "110"],
    }
    base.update(kw)
    return base


class TestHotendDetect(unittest.TestCase):
    def test_standard_from_nozzle_volume_type(self):
        info = hotend.detect(_settings())
        self.assertEqual(info.key, "standard")
        self.assertEqual(info.label, "标准流量")
        self.assertTrue(info.detected)
        self.assertEqual(info.source_key, "nozzle_volume_type")
        self.assertAlmostEqual(info.nozzle_volume, 110.0)

    def test_high_flow(self):
        info = hotend.detect(_settings(nozzle_volume_type=["High Flow"]))
        self.assertEqual(info.key, "high")
        self.assertEqual(info.label, "高流量")

    def test_e3d_not_stolen_by_high(self):
        info = hotend.detect(_settings(nozzle_volume_type=["E3D High Flow"]))
        self.assertEqual(info.key, "e3d", "e3d 必须先于 high 判定")

    def test_variant_fallback_when_no_volume_type(self):
        s = _settings()
        s.pop("nozzle_volume_type")
        s.pop("default_nozzle_volume_type")
        s.pop("extruder_nozzle_stats")
        s["printer_extruder_variant"] = ["Direct Drive E3D High Flow"]
        info = hotend.detect(s)
        self.assertEqual(info.key, "e3d")
        self.assertEqual(info.source_key, "printer_extruder_variant")

    def test_nothing_found_is_standard_but_not_detected(self):
        info = hotend.detect({})
        self.assertEqual(info.key, "standard")
        self.assertFalse(info.detected)
        self.assertIn("没读到流量类型", info.summary_line())

    def test_normalize_variants(self):
        for raw, want in (("High Flow#1", "high"), ("Direct Drive Standard", "standard"),
                          ("E3D", "e3d"), ("高流量", "high"), ("", ""),
                          ("Unknown Thing", "")):
            self.assertEqual(hotend.normalize(raw), want, raw)


class TestHotendFactor(unittest.TestCase):
    def setUp(self):
        self.rules = rules_engine.load_rules()

    def test_factors_never_shrink(self):
        for key in ("standard", "high", "e3d", "不存在的类型"):
            mul, _ = hotend.factor(self.rules, key)
            self.assertGreaterEqual(mul, 1.0, key)
        self.assertGreater(hotend.factor(self.rules, "high")[0],
                           hotend.factor(self.rules, "standard")[0])
        self.assertGreater(hotend.factor(self.rules, "e3d")[0],
                           hotend.factor(self.rules, "high")[0])

    def test_options_lists_auto_first(self):
        opts = hotend.options(self.rules)
        self.assertEqual(opts[0][0], "")
        keys = [k for k, _ in opts]
        for k in ("standard", "high", "e3d"):
            self.assertIn(k, keys)


@unittest.skipUnless(PROJ.exists(), "真实工程不存在")
class TestHotendAffectsResult(unittest.TestCase):
    def _run(self, flow):
        proj = threemf.ThreeMfProject.load(PROJ)
        rules = rules_engine.load_rules()
        from core import detector, hardware
        hw = hardware.read(proj)
        det = detector.detect(proj, rules)
        eng = rules_engine.RulesEngine(rules)
        return eng.optimize(proj.settings, printer_key=det.printer_key,
                            filament_key=det.filament_key, nozzle=0.4,
                            mode_key="balanced", hardware_info=hw,
                            hotend_flow=flow)

    def test_high_flow_raises_cap_and_speed(self):
        std = self._run("standard")
        high = self._run("high")
        self.assertGreater(high.flow_limit, std.flow_limit,
                           "高流量热端必须放宽流量上限")
        self.assertGreaterEqual(float(high.values["inner_wall_speed"]),
                                float(std.values["inner_wall_speed"]))
        self.assertTrue(any("热端流量类型" in n for n in high.notes))
        self.assertIn("高流量", high.hotend)

    def test_auto_matches_project(self):
        auto = self._run(None)
        std = self._run("standard")
        self.assertAlmostEqual(auto.flow_limit, std.flow_limit, places=3)


class TestWriter(unittest.TestCase):
    def test_studio_settings_stringifies(self):
        proj = threemf.ThreeMfProject.load(PROJ) if PROJ.exists() else None
        if proj is None:
            self.skipTest("真实工程不存在")
        proj.settings["__num_probe__"] = 0.25
        proj.settings["__list_probe__"] = [1, 2.5, True]
        out = proj.studio_settings()
        self.assertEqual(out["__num_probe__"], "0.25")
        self.assertEqual(out["__list_probe__"], ["1", "2.5", "1"])

    def test_mark_custom_process_renames_and_is_idempotent(self):
        if not PROJ.exists():
            self.skipTest("真实工程不存在")
        proj = threemf.ThreeMfProject.load(PROJ)
        before = str(proj.settings.get("print_settings_id") or "")
        first = proj.mark_custom_process()
        self.assertTrue(first.endswith(" - Smart Tuner"))
        second = proj.mark_custom_process()
        self.assertEqual(first, second, "重复保存不能无限加后缀")
        self.assertEqual(proj.settings.get("default_print_profile"),
                         proj.settings.get("print_settings_id"))
        self.assertTrue(before)

    def test_guard_blocks_preset_dirs(self):
        dirs = safety.preset_dirs()
        if not dirs:
            self.skipTest("这台机器上没有 Bambu Studio 预设目录")
        target = dirs[0] / "should_not_write.json"
        with self.assertRaises(PermissionError):
            safety.guard_target(target)

    def test_guard_allows_normal_target(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.3mf"
            self.assertEqual(safety.guard_target(p).name, "a.3mf")

    def test_guard_rejects_weird_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PermissionError):
                safety.guard_target(Path(td) / "a.exe")

    def test_self_check_detects_mismatch(self):
        if not PROJ.exists():
            self.skipTest("真实工程不存在")
        with tempfile.TemporaryDirectory() as td:
            proj = threemf.ThreeMfProject.load(PROJ)
            proj.apply({"wall_loops": "7"})
            preset_diff.apply_to_project(proj, also=["wall_loops"])
            out = proj.save_as(Path(td) / "x.3mf")
            self.assertEqual(safety.self_check(out, {"wall_loops": "7"}), [])
            bad = safety.self_check(out, {"wall_loops": "9"})
            self.assertEqual(len(bad), 1)
            self.assertIn("wall_loops", bad[0])

    def test_self_check_flags_empty_process_diff(self):
        """工艺差异声明为空 = Studio 会用预设值覆盖，必须报出来。"""
        if not PROJ.exists():
            self.skipTest("真实工程不存在")
        with tempfile.TemporaryDirectory() as td:
            proj = threemf.ThreeMfProject.load(PROJ)
            proj.apply({"wall_loops": "7"})
            proj.settings["different_settings_to_system"] = '["", "", ""]'
            out = proj.save_as(Path(td) / "y.3mf")
            bad = safety.self_check(out, {"wall_loops": "7"})
            self.assertTrue(any("different_settings_to_system" in x for x in bad), bad)

    def test_written_file_has_no_numeric_values(self):
        """写出的 project_settings.config 里不该出现数字/布尔的裸值。"""
        if not PROJ.exists():
            self.skipTest("真实工程不存在")
        with tempfile.TemporaryDirectory() as td:
            proj = threemf.ThreeMfProject.load(PROJ)
            proj.apply({"layer_height": "0.24"})
            out = proj.save_as(Path(td) / "y.3mf")
            with zipfile.ZipFile(out) as z:
                name = [n for n in z.namelist() if n.endswith("project_settings.config")][0]
                data = json.loads(z.read(name).decode("utf-8"))
            bad = [(k, type(v).__name__) for k, v in data.items()
                   if not isinstance(v, (str, list))]
            self.assertEqual(bad, [], f"这些值不是字符串：{bad[:5]}")
            for k, v in data.items():
                if isinstance(v, list):
                    self.assertTrue(
                        all(isinstance(x, str) for x in v),
                        f"{k} 数组里有非字符串元素：{v!r}")


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
        from core import wall_compat
        for val in ("0", "false", "", None):
            ops, warns, notes = wall_compat.check(
                {"wall_loops": 6}, project={"alternate_extra_wall": val})
            self.assertEqual(ops, {})
            self.assertEqual(warns, [])
            self.assertEqual(notes, [])

    def test_schema_has_partial_choice(self):
        from core import schema
        sp = schema.PARAMS["ensure_vertical_shell_thickness"]
        self.assertIn("partial", sp.choices)

    def test_engine_writes_zero_and_warns(self):
        import io as _io
        from core import hardware
        eng = rules_engine.RulesEngine(json.load(_io.open("rules/BambuRules.json", encoding="utf-8-sig")))
        prj = threemf.ThreeMfProject.load(PROJECT)
        prj.settings["alternate_extra_wall"] = "1"
        hw = hardware.read(prj)
        res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG",
                           nozzle=0.4, mode_key="strength", hardware_info=hw,
                           nozzle_explicit=True)
        self.assertIn("alternate_extra_wall", res.write_values)
        self.assertIn(str(res.write_values["alternate_extra_wall"]).lower(), ("0", "false"))
        self.assertTrue(any("交替额外墙" in w for w in res.warnings))


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
