"""自定义耗材同步 + 模型形状自适应的回归测试。

依赖真实 Bambu Studio 安装的部分会自动跳过（没有装也不会失败）。
运行：python tests/test_features.py -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from core import bambu_profiles as bp          # noqa: E402
from core import detector, model_analysis, rules_engine, schema, threemf   # noqa: E402
from make_sample_3mf import build_sample      # noqa: E402
from make_shape_samples import SHAPES, build as build_shape                # noqa: E402

RULES = rules_engine.load_rules()
ENGINE = rules_engine.RulesEngine(RULES)
HAS_SYSTEM_PROFILES = bool(bp.system_profile_dirs())


class TestOverlayIntegration(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.path = build_sample(Path(self.td) / "s.3mf")
        self.proj = threemf.ThreeMfProject.load(self.path)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_overlay_overrides_baseline(self):
        """自定义耗材覆盖层：耗材页的键只读不改，但覆盖值要参与计算与说明。"""
        overlay = {
            "label": "彩格petg", "family": "PETG",
            "limits": {"max_volumetric_speed": 12},
            "baseline": {"fan_min_speed": 55, "fan_max_speed": 75,
                         "filament_flow_ratio": 0.95, "retraction_length": 0.8},
        }
        res = ENGINE.optimize(self.proj.settings, printer_key="X1C", filament_key="PETG",
                              nozzle=0.4, mode_key="balanced", filament_overlay=overlay)
        # 耗材页 / 机器页的键：算出��覆盖值，但一个字都不写
        self.assertAlmostEqual(res.values["fan_max_speed"], 75, places=3)
        self.assertNotIn("fan_max_speed", res.write_values)
        self.assertNotIn("retraction_length", res.write_values)
        self.assertTrue(any("彩格petg" in n for n in res.notes))
        # 有 overlay 的理由要出现在对应行的 reason 里
        row = next(r for r in res.rows if r.key == "fan_max_speed")
        self.assertIn("自定义耗材", row.reason)
        self.assertFalse(row.will_write)

    def test_overlay_volumetric_cap(self):
        overlay = {"label": "慢料", "family": "PETG",
                   "limits": {"max_volumetric_speed": 3}, "baseline": {}}
        res = ENGINE.optimize(self.proj.settings, printer_key="X1C", filament_key="PETG",
                             nozzle=0.4, mode_key="strength", filament_overlay=overlay)
        lh = res.values["layer_height"]
        lw = res.values["sparse_infill_line_width"]
        self.assertLessEqual(res.values["sparse_infill_speed"], 3 / (lh * lw) + 0.2)
        self.assertTrue(any("体积流量" in w for w in res.warnings))

    def test_no_overlay_unchanged_behaviour(self):
        a = ENGINE.optimize(self.proj.settings, printer_key="X1C", filament_key="PLA",
                            nozzle=0.4, mode_key="balanced")
        b = ENGINE.optimize(self.proj.settings, printer_key="X1C", filament_key="PLA",
                            nozzle=0.4, mode_key="balanced", filament_overlay={})
        self.assertEqual(a.write_values, b.write_values)


class TestProfileScanning(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        # 造一个假系统预设树
        self.sysprof = self.td / "profiles"
        (self.sysprof / "BBL" / "filament").mkdir(parents=True)
        (self.sysprof / "BBL" / "filament" / "fdm_filament_pet.json").write_text(json.dumps({
            "type": "filament", "name": "fdm_filament_pet", "from": "system",
            "fan_min_speed": ["40"], "fan_max_speed": ["90"],
            "filament_flow_ratio": ["0.95"],
            "filament_max_volumetric_speed": ["12"],
        }), encoding="utf-8")
        (self.sysprof / "BBL" / "filament" / "Generic PETG @BBL P2S.json").write_text(json.dumps({
            "type": "filament", "name": "Generic PETG @BBL P2S", "from": "system",
            "inherits": "fdm_filament_pet", "filament_type": ["PETG"],
        }), encoding="utf-8")
        # 造一个用户自定义
        self.user = self.td / "user"
        (self.user / "filament").mkdir(parents=True)
        (self.user / "filament" / "彩格petg.json").write_text(json.dumps({
            "type": "filament", "name": "彩格petg", "from": "User",
            "inherits": "Generic PETG @BBL P2S",
            "filament_max_volumetric_speed": ["9"],
            "fan_max_speed": ["70"],
            "nozzle_temperature": ["240"],
        }, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_scan_and_resolve(self):
        presets = bp.scan(roots=[("bambu", self.user)], system_dirs=[self.sysprof])
        self.assertEqual(len(presets), 1)
        p = presets[0]
        self.assertEqual(p.name, "彩格petg")
        self.assertEqual(p.family, "PETG")
        self.assertEqual(p.volumetric_speed, 9)      # 用户覆盖优先
        self.assertEqual(p.fan_max, 70)
        self.assertEqual(p.fan_min, 40)              # 继承来的
        self.assertEqual(p.flow_ratio, 0.95)
        self.assertIn("Generic PETG @BBL P2S", p.chain)
        self.assertTrue(p.resolvable)

    def test_overlay_payload(self):
        p = bp.scan(roots=[("bambu", self.user)], system_dirs=[self.sysprof])[0]
        ov = bp.to_overlay(p)
        self.assertEqual(ov["family"], "PETG")
        self.assertEqual(ov["limits"]["max_volumetric_speed"], 9)
        self.assertIn("fan_max_speed", ov["baseline"])

    def test_empty_dir_no_crash(self):
        empty = self.td / "nothing"
        self.assertEqual(bp.scan(roots=[("bambu", empty)], system_dirs=[]), [])


@unittest.skipUnless(HAS_SYSTEM_PROFILES, "本机没有安装 Bambu Studio，跳过真实预设测试")
class TestRealProfiles(unittest.TestCase):
    def test_real_scan(self):
        presets = bp.scan()
        self.assertGreater(len(presets), 0, "扫不到本机自定义耗材")
        for p in presets:
            self.assertIn(p.family, ("PLA", "PETG", "ASA", "ABS", "TPU"))
            if p.resolvable:
                self.assertTrue(p.chain, p.name)

    def test_real_overlay_usable(self):
        presets = [p for p in bp.scan() if p.resolvable and p.volumetric_speed]
        self.assertTrue(presets, "没有可用的自定义耗材")
        p = presets[0]
        ov = bp.to_overlay(p)
        with tempfile.TemporaryDirectory() as td:
            proj = threemf.ThreeMfProject.load(build_sample(Path(td) / "a.3mf"))
            res = ENGINE.optimize(proj.settings, printer_key="X1C",
                                  filament_key=p.family, nozzle=0.4,
                                  mode_key="balanced", filament_overlay=ov)
        self.assertIn("values", vars(res))


class TestModelAnalysis(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _profile(self, stem):
        geom, _ = SHAPES[stem]
        p = build_shape(self.td / f"{stem}.3mf", geom, stem)
        return model_analysis.analyse(threemf.ThreeMfProject.load(p))

    def test_volume_accuracy_box(self):
        # 160×120×8 = 153600 mm³
        prof = self._profile("shape_plate_flat")
        self.assertAlmostEqual(prof.volume, 160 * 120 * 8, delta=200)
        self.assertAlmostEqual(prof.size_x, 160, delta=1)
        self.assertAlmostEqual(prof.size_z, 8, delta=0.5)

    def test_cylinder_volume(self):
        import math
        prof = self._profile("shape_vase_tall")
        expect = math.pi * 30 ** 2 * 190
        self.assertAlmostEqual(prof.volume, expect, delta=expect * 0.03)

    def test_plate_not_counted_as_overhang(self):
        prof = self._profile("shape_plate_flat")
        self.assertLess(prof.support_ratio, 0.02, f"平板不该有悬垂：{prof.support_ratio}")

    def test_tall_is_slender(self):
        prof = self._profile("shape_vase_tall")
        self.assertGreater(prof.slender, 2.5)
        self.assertIn("高瘦易晃", prof.tags())
        self.assertGreater(prof.layers, 800)

    def test_tower_overhang_detected(self):
        prof = self._profile("shape_tower_overhang")
        self.assertGreater(prof.support_ratio, 0.03)

    def test_suggestions_shrink_high_speed(self):
        prof = self._profile("shape_vase_tall")
        ops, notes = model_analysis.suggestions(prof, layer_height=0.2, mode="quality")
        self.assertIn("outer_wall_acceleration", ops)
        self.assertLess(ops["outer_wall_acceleration"]["mul"], 1.0)
        self.assertTrue(notes)

    def test_engine_applies_shape_layer(self):
        geom, _ = SHAPES["shape_vase_tall"]
        p = build_shape(self.td / "v.3mf", geom, "vase")
        proj = threemf.ThreeMfProject.load(p)
        base = ENGINE.optimize(proj.settings, printer_key="X1C", filament_key="PLA",
                              nozzle=0.4, mode_key="balanced")
        shaped = ENGINE.optimize(proj.settings, printer_key="X1C", filament_key="PLA",
                                nozzle=0.4, mode_key="balanced",
                                model_profile=model_analysis.analyse(proj))
        self.assertLess(shaped.values["outer_wall_acceleration"],
                        base.values["outer_wall_acceleration"])
        self.assertGreaterEqual(shaped.values["brim_width"], base.values["brim_width"])
        self.assertTrue(any("细高比" in n for n in shaped.notes))

    def test_broken_mesh_raises(self):
        p = self.td / "bad.3mf"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("3D/3dmodel.model", "<model/>")
            z.writestr("Metadata/project_settings.config", "{}")
        proj = threemf.ThreeMfProject.load(p)
        with self.assertRaises(model_analysis.ModelError):
            model_analysis.analyse(proj)


class TestTimeCap(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.proj = threemf.ThreeMfProject.load(build_sample(Path(self.td) / "s.3mf"))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_cap_pulls_back(self):
        free = ENGINE.optimize(self.proj.settings, printer_key="A1mini",
                               filament_key="TPU", nozzle=0.4, mode_key="quality")
        capped = ENGINE.optimize(self.proj.settings, printer_key="A1mini",
                                 filament_key="TPU", nozzle=0.4, mode_key="quality",
                                 time_cap_pct=25)
        if free.time.delta_pct > 25:
            # 达不到上限时必须更短，并且必须给出明确告警
            self.assertLess(capped.time.delta_pct, free.time.delta_pct)
            self.assertTrue(any("时长上限" in t
                                for t in capped.warnings + capped.notes))
        else:
            self.assertAlmostEqual(capped.time.delta_pct, free.time.delta_pct, delta=0.5)

    def test_cap_respects_limits_after_pullback(self):
        """回调把速度提回后，仍不能突破体积流量与机型上限。"""
        res = ENGINE.optimize(self.proj.settings, printer_key="A1mini",
                              filament_key="TPU", nozzle=0.4, mode_key="quality",
                              time_cap_pct=60)
        lh = res.values["layer_height"]
        lw = res.values["sparse_infill_line_width"]
        self.assertLessEqual(res.values["sparse_infill_speed"], 6 / (lh * lw) + 0.5)
        # A1 mini 官方上限（0.4 喷嘴档）：速度 500、加速度 20000、空走加速度 9000
        self.assertLessEqual(res.values["outer_wall_speed"], 500 + 1e-6)
        self.assertLessEqual(res.values["default_acceleration"], 20000 + 1e-6)
        self.assertLessEqual(res.values["travel_acceleration"], 9000 + 1e-6)

    def test_strength_mode_ignores_cap_when_none(self):
        ENGINE.last_timecap = None
        ENGINE.optimize(self.proj.settings, printer_key="A1mini", filament_key="TPU",
                        nozzle=0.4, mode_key="strength")
        self.assertIsNone(ENGINE.last_timecap)

    def test_cap_state_recorded(self):
        ENGINE.optimize(self.proj.settings, printer_key="A1mini", filament_key="TPU",
                        nozzle=0.4, mode_key="quality", time_cap_pct=20)
        cap = ENGINE.last_timecap
        self.assertIsNotNone(cap)
        self.assertEqual(cap["cap"], 20)
        self.assertLessEqual(cap["after"], cap["before"] + 0.01)

    def test_no_cap_no_record(self):
        ENGINE.last_timecap = None
        ENGINE.optimize(self.proj.settings, printer_key="X1C", filament_key="PLA",
                        nozzle=0.4, mode_key="balanced")
        self.assertIsNone(ENGINE.last_timecap)


if __name__ == "__main__":
    unittest.main(verbosity=2)
