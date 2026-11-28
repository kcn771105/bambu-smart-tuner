"""裙边定量（core/adhesion.py）与支撑按模型（core/support_model.py）的回归测试。"""
from __future__ import annotations

import io
import unittest

from core import adhesion, support_model
from core.model_analysis import ModelProfile, ObjectProfile


def obj(sx, sy, sz, *, volume=None, footprint_override=None, overhang=0.0,
        offset=0.0, oid="o1", index=1):
    o = ObjectProfile(oid=oid, index=index, size_x=sx, size_y=sy, size_z=sz,
                      min_z=0.0, max_z=sz,
                      volume=volume if volume is not None else sx * sy * sz * 0.6,
                      surface=2 * (sx * sy + sx * sz + sy * sz),
                      overhang_area=overhang, centre_offset=offset)
    return o


class TestAdhesionRisk(unittest.TestCase):
    def test_tall_thin_needs_wide_brim(self):
        p = obj(10, 10, 120, volume=10_000)
        d = adhesion.decide(p, filament_key="PLA", current={"brim_width": 0})
        self.assertGreaterEqual(d.tip, 8.0)
        self.assertEqual(d.width, 10.0)
        self.assertEqual(d.brim_type, "outer_only")
        self.assertIn("brim_width", d.ops)

    def test_flat_plate_keeps_brim(self):
        p = obj(120, 120, 4, volume=50_000)
        d = adhesion.decide(p, current={"brim_width": 5})
        self.assertFalse(d.ops)
        self.assertIn("保持工程原值", " ".join(d.reasons))

    def test_small_part_gets_floor(self):
        p = obj(20, 20, 8, volume=2_000)
        d = adhesion.decide(p, current={"brim_width": 0})
        self.assertTrue(d.small_part)
        self.assertGreaterEqual(d.width, 3.0)

    def test_abs_widens_more_than_pla(self):
        p = obj(12, 12, 90, volume=8_000)
        pla = adhesion.decide(p, filament_key="PLA", current={"brim_width": 0})
        abs_ = adhesion.decide(p, filament_key="ABS", current={"brim_width": 0})
        self.assertGreater(abs_.width, pla.width)

    def test_wider_existing_brim_not_reduced(self):
        p = obj(10, 10, 120, volume=10_000)
        d = adhesion.decide(p, filament_key="PLA", current={"brim_width": 15})
        self.assertNotIn("brim_width", d.ops)          # 不往回收
        self.assertIn("保留原值", " ".join(d.reasons))

    def test_multi_object_takes_widest(self):
        a = obj(10, 10, 120, volume=10_000, oid="a", index=1)
        b = obj(60, 60, 6, volume=20_000, oid="b", index=2)
        prof = ModelProfile(objects=[a, b])
        ops, notes, rows = adhesion.tune(prof, current={"brim_width": 0})
        self.assertEqual(ops.get("brim_width"), {"set": 10.0})
        self.assertTrue(any("件1" in r.metric for r in rows))

    def test_offset_increases_risk(self):
        base = obj(20, 20, 60, volume=20_000, offset=0.0)
        off = obj(20, 20, 60, volume=20_000, offset=10.0)
        self.assertGreater(adhesion.risk_of(off)[0], adhesion.risk_of(base)[0])


class TestSupportModel(unittest.TestCase):
    def _prof(self, **kw):
        return ModelProfile(objects=[obj(40, 40, 80, volume=60_000, **kw)])

    def test_disabled_support_does_nothing(self):
        t = support_model.tune(self._prof(overhang=2000), values={"enable_support": 0})
        self.assertFalse(t.ops)

    def test_large_overhang_dense(self):
        t = support_model.tune(self._prof(overhang=5000), values={"enable_support": 1})
        self.assertEqual(t.ops["support_base_pattern_spacing"], {"set": 1.6})
        self.assertEqual(t.ops["support_type"], {"set": "normal(auto)"})
        self.assertEqual(t.ops["support_base_pattern"], {"set": "grid"})

    def test_tiny_overhang_sparse(self):
        t = support_model.tune(self._prof(overhang=120), values={"enable_support": 1})
        self.assertEqual(t.ops["support_base_pattern_spacing"], {"set": 3.0})

    def test_tall_slim_uses_tree_strong(self):
        tall = ModelProfile(objects=[obj(12, 12, 200, volume=20_000, overhang=800)])
        t = support_model.tune(tall, values={"enable_support": 1})
        self.assertEqual(t.ops["support_type"], {"set": "tree(auto)"})
        self.assertEqual(t.ops["support_style"], {"set": "tree_strong"})
        self.assertEqual(t.ops["support_object_xy_distance"], {"set": 0.9})

    def test_top_z_follows_layer_height(self):
        p = self._prof(overhang=2000)
        thin = support_model.tune(p, layer_height=0.12, values={"enable_support": 1})
        thick = support_model.tune(p, layer_height=0.28, values={"enable_support": 1})
        self.assertAlmostEqual(thin.ops["support_top_z_distance"]["set"], 0.12, places=2)
        self.assertAlmostEqual(thick.ops["support_top_z_distance"]["set"], 0.2, places=2)


class TestEngineIntegration(unittest.TestCase):
    def _engine(self):
        from core import rules_engine
        return rules_engine.RulesEngine(rules_engine.load_rules())

    def test_engine_writes_brim_for_tall_thin(self):
        eng = self._engine()
        current = {
            "brim_width": "0", "layer_height": "0.2", "line_width": "0.42",
            "enable_support": "0", "support_threshold_angle": "30",
            "wall_loops": "2", "sparse_infill_density": "15%",
            "printer_model": "Bambu Lab P2S", "filament_type": "PLA",
            "nozzle_diameter": "0.4",
        }
        prof = ModelProfile(objects=[obj(10, 10, 120, volume=10_000)])
        res = eng.optimize(current, printer_key="P2S", filament_key="PLA",
                           nozzle=0.4, mode_key="balanced", model_profile=prof,
                           nozzle_explicit=True)
        self.assertGreater(float(res.write_values.get("brim_width", 0)), 0.0)
        self.assertTrue(any("裙边" in d["metric"] for d in res.derivations))

    def test_engine_support_rows_appear(self):
        eng = self._engine()
        current = {
            "brim_width": "5", "layer_height": "0.2", "line_width": "0.42",
            "enable_support": "1", "support_threshold_angle": "30",
            "wall_loops": "2", "sparse_infill_density": "15%",
            "printer_model": "Bambu Lab P2S", "filament_type": "PLA",
            "nozzle_diameter": "0.4",
        }
        prof = ModelProfile(objects=[obj(40, 40, 80, volume=60_000, overhang=5000)])
        res = eng.optimize(current, printer_key="P2S", filament_key="PLA",
                           nozzle=0.4, mode_key="strength", model_profile=prof,
                           nozzle_explicit=True)
        self.assertTrue(any("支撑" in d["metric"] for d in res.derivations))


class TestSupportModelSingleSource(unittest.TestCase):
    """支撑定量参数唯一来源：core/support_model.py。"""

    def _profile(self, overhang=600.0, size_z=40.0, foot=1600.0):
        obj = ObjectProfile(
            oid="1", index=0, size_x=40, size_y=40, size_z=size_z,
            min_z=0, max_z=size_z, volume=64_000, surface=9_600,
            overhang_area=overhang)
        return ModelProfile(
            objects=[obj], triangles=12, size_x=40, size_y=40, size_z=size_z,
            volume=obj.volume, surface=obj.surface,
            overhang_area=overhang, footprint=foot)

    def test_support_off_writes_nothing(self):
        su = support_model.tune(self._profile(), layer_height=0.2,
                                mode="balanced", values={"enable_support": 0})
        self.assertEqual(su.ops, {})

    def test_sparse_overhang_gets_loose_spacing(self):
        su = support_model.tune(self._profile(overhang=100), layer_height=0.2,
                                mode="balanced", values={"enable_support": 1})
        self.assertEqual(su.ops["support_base_pattern_spacing"], {"set": 3.0})

    def test_heavy_overhang_gets_dense_spacing_and_thick_interface(self):
        su = support_model.tune(self._profile(overhang=5000), layer_height=0.2,
                                mode="strength", values={"enable_support": 1})
        self.assertEqual(su.ops["support_base_pattern_spacing"], {"set": 1.6})
        self.assertEqual(su.ops["support_interface_top_layers"], {"set": 3})
        self.assertEqual(su.ops["support_interface_spacing"], {"set": 0.5})

    def test_gap_follows_layer_height(self):
        su = support_model.tune(self._profile(), layer_height=0.12,
                                mode="balanced", values={"enable_support": 1})
        self.assertEqual(su.ops["support_top_z_distance"], {"set": 0.12})
        self.assertGreaterEqual(su.ops["support_bottom_z_distance"]["set"], 0.15)

    def test_slender_gets_tree_strong(self):
        su = support_model.tune(self._profile(size_z=190, foot=900),
                                layer_height=0.2, mode="quality",
                                values={"enable_support": 1})
        self.assertEqual(su.ops["support_type"], {"set": "tree(auto)"})
        self.assertEqual(su.ops["support_style"], {"set": "tree_strong"})

    def test_speed_scales_with_mode_and_cap(self):
        base = dict(layer_height=0.2, values={"enable_support": 1})
        slow = support_model.tune(self._profile(), mode="ultrafine", max_speed=600, **base)
        fast = support_model.tune(self._profile(), mode="draft", max_speed=600, **base)
        self.assertLess(slow.ops["support_speed"]["set"], fast.ops["support_speed"]["set"])
        self.assertLessEqual(fast.ops["support_speed"]["set"], 600)
        # 接触面永远比本体慢
        self.assertLess(slow.ops["support_interface_speed"]["set"],
                        slow.ops["support_speed"]["set"])

    def test_quality_family_turns_on_ironing(self):
        su = support_model.tune(self._profile(), layer_height=0.16, mode="quality",
                                values={"enable_support": 1})
        self.assertEqual(su.ops["support_critical_regions_only"], {"set": True})
        self.assertIn("support_ironing_flow", su.ops)
        self.assertIn("support_ironing_spacing", su.ops)

    def test_balanced_does_not_touch_ironing(self):
        su = support_model.tune(self._profile(), layer_height=0.2, mode="balanced",
                                values={"enable_support": 1})
        self.assertNotIn("support_ironing_flow", su.ops)

    def test_rows_are_explainable(self):
        su = support_model.tune(self._profile(), layer_height=0.2, mode="balanced",
                                values={"enable_support": 1})
        self.assertTrue(su.rows)
        for r in su.rows:
            self.assertTrue(r.formula and r.conclusion)


class TestSupportFlowClamp(unittest.TestCase):
    """流量钳制之后，支撑接触面仍必须比本体慢。"""

    def test_engine_keeps_interface_slower(self):
        import json as _json
        from pathlib import Path as _Path

        from core import hardware
        from core.rules_engine import RulesEngine
        from core.threemf import ThreeMfProject

        root = _Path(__file__).resolve().parent.parent
        src = _Path(__import__("tests._sample", fromlist=["PROJ"]).PROJ)
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


class TestSupportSwitch(unittest.TestCase):
    """支撑开关：auto / on / off（用户要求「开启支撑需要手动调整」）。"""

    def _run(self, mode_key):
        import json as _json
        from pathlib import Path as _Path

        from core import hardware
        from core.rules_engine import RulesEngine
        from core.threemf import ThreeMfProject

        src = _Path(__import__("tests._sample", fromlist=["PROJ"]).PROJ)
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


if __name__ == "__main__":
    unittest.main()
