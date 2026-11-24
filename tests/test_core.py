"""核心层单元测试（不需要 GUI，不需要真机文件）

运行：
    python tests/test_core.py -v
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

from core import detector, report, rules_engine, schema, scope, threemf   # noqa: E402
from make_sample_3mf import build_sample                            # noqa: E402

RULES = rules_engine.load_rules()
ENGINE = rules_engine.RulesEngine(RULES)


class TestRulesLibrary(unittest.TestCase):
    def test_validate_clean(self):
        problems = ENGINE.validate()
        self.assertEqual(problems, [], f"规则库自检有问题：{problems}")

    def test_all_modes_exist(self):
        keys = [k for k, _ in ENGINE.mode_choices()]
        for k in ("strength", "quality", "balanced"):
            self.assertIn(k, keys)

    def test_defaults_cover_core_params(self):
        missing = [k for k, s in schema.PARAMS.items()
                   if not s.soft and k not in RULES["defaults"]]
        self.assertEqual(missing, [], f"defaults 缺少必需参数：{missing}")

    def test_every_printer_has_limits(self):
        for key, node in RULES["printers"].items():
            self.assertIn("limits", node, key)
            self.assertIn("max_speed", node["limits"], key)
            self.assertIn("max_accel", node["limits"], key)
            self.assertIn("max_volumetric_speed", node["limits"], key)
            self.assertTrue(node.get("label"), key)


class TestSchemaFormat(unittest.TestCase):
    def test_percent(self):
        s = schema.PARAMS["sparse_infill_density"]
        self.assertEqual(schema.format_value(s, 15), "15%")
        self.assertEqual(schema.parse_value(s, "15%"), 15.0)

    def test_array_keeps_length(self):
        s = schema.PARAMS["pressure_advance"]
        # Bambu 的数组元素一律是字符串，且长度按原来的槽位数复制。
        # 数组是按喷嘴/耗材分槽的：只改第 0 槽（本次优化的喷嘴），
        # 其余槽位保持用户原值——否则会把用户其它喷嘴的设定一起改掉。
        self.assertEqual(schema.format_value(s, 0.035, '["0.02"]'), '["0.035"]')
        self.assertEqual(schema.format_value(s, 0.035, '["0.02", "0.03"]'),
                         '["0.035", "0.03"]')
        self.assertAlmostEqual(schema.parse_value(s, '["0.02", "0.03"]'), 0.02)

    def test_array_pct(self):
        s = schema.PARAMS["small_perimeter_speed"]
        self.assertEqual(schema.parse_value(s, '["50%", "50%"]'), 50.0)
        self.assertEqual(schema.format_value(s, 65, '["50%", "50%"]'), '["65%", "50%"]')

    def test_array_keeps_user_slots(self):
        """真实工程里 outer_wall_speed 是 ["200","500","500"]：只动第 0 槽。"""
        s = schema.PARAMS["outer_wall_speed"]
        self.assertEqual(schema.format_value(s, 136, '["200", "500", "500"]'),
                         '["136", "500", "500"]')

    def test_scalar_stays_scalar(self):
        """原值是标量时不要写成数组（否则 Bambu 读不懂）。"""
        s = schema.PARAMS["layer_height"]
        self.assertEqual(schema.format_value(s, 0.16, "0.2"), "0.16")

    def test_percent_follow_semantics_kept(self):
        """官方用 "100%" 表示「跟随默认加速度」，写回时必须保住 % 号。"""
        s = schema.PARAMS["sparse_infill_acceleration"]
        self.assertEqual(schema.format_value(s, 100, '["100%", "100%"]'),
                         '["100%", "100%"]')

    def test_enum_array(self):
        s = schema.PARAMS["cooling_slowdown_logic"]
        self.assertEqual(schema.parse_value(s, '["uniform_cooling"]'), "uniform_cooling")
        self.assertEqual(schema.format_value(s, "minimum_layer_time", '["uniform_cooling"]'),
                         '["minimum_layer_time"]')

    def test_bool_style(self):
        s = schema.PARAMS["reduce_crossing_wall"]
        self.assertEqual(schema.format_value(s, True, "1"), "1")
        self.assertEqual(schema.format_value(s, False, "1"), "0")
        self.assertEqual(schema.format_value(s, True, "true"), "true")

    def test_clamp(self):
        s = schema.PARAMS["outer_wall_speed"]
        self.assertEqual(schema.clamp(s, 5000), 1000)
        self.assertEqual(schema.clamp(s, 1), 10)


class TestDetection(unittest.TestCase):
    def _detect(self, printer, filament, nozzle=0.4):
        with tempfile.TemporaryDirectory() as td:
            p = build_sample(Path(td) / "a.3mf", printer_model=printer,
                             filament=filament, nozzle=nozzle)
            proj = threemf.ThreeMfProject.load(p)
        return detector.detect(proj, RULES)

    def test_all_printers(self):
        for key, node in RULES["printers"].items():
            if key == "GENERIC":
                continue
            for alias in node["aliases"][:2]:
                det = self._detect(alias, "PLA")
                self.assertEqual(det.printer_key, key, f"{alias} 识别成 {det.printer_key}")

    def test_filaments(self):
        cases = {"PLA": "PLA", "PLA-CF": "PLA", "PETG HF": "PETG",
                 "ASA-CF": "ASA", "ABS-GF": "ABS", "TPU 95A": "TPU"}
        for raw, expect in cases.items():
            det = self._detect("Bambu Lab X1 Carbon", raw)
            self.assertEqual(det.filament_key, expect, f"{raw} 识别成 {det.filament_key}")

    def test_unknown_falls_back(self):
        det = self._detect("Some Unknown Printer 9000", "PMAA")
        self.assertEqual(det.printer_key, "GENERIC")
        self.assertEqual(det.filament_key, "GENERIC")
        self.assertFalse(det.printer_confident)
        self.assertTrue(det.warnings)

    def test_nozzle(self):
        det = self._detect("Bambu Lab P1S", "PLA", nozzle=0.6)
        self.assertAlmostEqual(det.nozzle, 0.6)


class TestOptimize(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.path = build_sample(Path(self.td) / "sample.3mf")
        self.proj = threemf.ThreeMfProject.load(self.path)
        self.det = detector.detect(self.proj, RULES)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _run(self, mode, printer="X1C", filament="PLA", nozzle=0.4):
        return ENGINE.optimize(self.proj.settings, printer_key=printer,
                               filament_key=filament, nozzle=nozzle, mode_key=mode,
                               detection_warnings=list(self.det.warnings),
                               detection_notes=list(self.det.notes))

    def _assert_legal(self, res):
        for row in res.rows:
            s = schema.PARAMS[row.key]
            if s.kind in (schema.ENUM, schema.BOOL):
                if s.kind == schema.ENUM and s.choices:
                    self.assertIn(row.new_value, s.choices, row.key)
                continue
            self.assertGreaterEqual(float(row.new_value), s.vmin - 1e-6, row.key)
            self.assertLessEqual(float(row.new_value), s.vmax + 1e-6, row.key)

    def test_modes_produce_changes(self):
        for mode in ("strength", "quality", "balanced"):
            res = self._run(mode)
            self.assertGreater(res.changed_count, 5, f"{mode} 没有产生足够改动")
            self._assert_legal(res)
            for k, v in res.write_values.items():
                self.assertIn(k, self.proj.settings, f"{k} 不在工程里却被写入")

    def test_strength_shape(self):
        """强度优先：墙层更多、密度更高、填充重叠更大、外壁更慢。

        数值口径对齐官方 0.20mm Strength @BBL X1C（wall_loops 6、密度 25%、
        填充图案 grid），强度档用「下限」表达，不会把用户已调高的强度改低。
        """
        res = self._run("strength")
        v = res.values
        self.assertGreaterEqual(v["wall_loops"], 6)
        self.assertGreaterEqual(v["sparse_infill_density"], 25)
        self.assertEqual(v["sparse_infill_pattern"], "grid")
        self.assertGreaterEqual(v["infill_wall_overlap"], 20)
        self.assertLessEqual(v["outer_wall_speed"], 200)

    def test_quality_shape(self):
        res = self._run("quality")
        v = res.values
        self.assertLess(v["layer_height"], 0.2)
        self.assertLessEqual(v["outer_wall_speed"], 130)
        self.assertEqual(v["top_surface_pattern"], "monotonic")

    def test_time_estimate_direction(self):
        strength = self._run("strength")
        quality = self._run("quality")
        self.assertGreater(strength.time.delta_pct, 0, "强度优先应该更慢")
        self.assertGreater(quality.time.delta_pct, 0, "质量优先层高变小，应该更慢")

    def test_machine_caps_a1_tpu(self):
        res = self._run("strength", printer="A1mini", filament="TPU", nozzle=0.4)
        v = res.values
        # A1 mini 官方机器上限（0.4 喷嘴档）：速度 500、加速度 20000、空走加速度 9000
        for k in ("outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
                  "top_surface_speed", "gap_infill_speed"):
            self.assertLessEqual(v[k], 500 + 1e-6, k)
        self.assertLessEqual(v["default_acceleration"], 20000 + 1e-6)
        self.assertLessEqual(v["outer_wall_acceleration"], 20000 + 1e-6)
        self.assertLessEqual(v["travel_acceleration"], 9000 + 1e-6)
        self.assertLessEqual(v["outer_wall_speed"], 60)   # TPU 上限 + A1 交叉规则

    def test_filament_page_keys_are_not_written(self):
        """耗材页 / 机器页的键只读不改：不出现在 write_values 里。"""
        res = self._run("strength", printer="A1mini", filament="TPU", nozzle=0.4)
        foreign = [k for k in res.write_values
                   if scope.scope_of(k) not in (scope.PROCESS,)]
        self.assertEqual(foreign, [], f"越权写入耗材页/机器页：{foreign}")
        # 压力提前属于耗材页，引擎里不再有它的取值
        self.assertNotIn("pressure_advance", res.values)

    def test_flow_guard(self):
        # 集成：A1 mini + TPU 的最终速度必须落在流量上限内
        res = self._run("strength", printer="A1mini", filament="TPU")
        lw = res.values["sparse_infill_line_width"]
        lh = res.values["layer_height"]
        self.assertLessEqual(res.values["sparse_infill_speed"], 6 / (lh * lw) + 0.2)

    def test_flow_guard_clamps_and_warns(self):
        # 直接灌超限值，验证钳制与告警一定发生
        from collections import defaultdict
        vals = {
            "layer_height": 0.3, "line_width": 0.6,
            "outer_wall_line_width": 0.6, "inner_wall_line_width": 0.6,
            "sparse_infill_line_width": 0.6, "internal_solid_infill_line_width": 0.6,
            "top_surface_line_width": 0.6,
            "outer_wall_speed": 500, "inner_wall_speed": 500,
            "sparse_infill_speed": 500, "internal_solid_infill_speed": 500,
            "top_surface_speed": 500, "gap_infill_speed": 500,
        }
        reasons = defaultdict(list)
        warnings: list[str] = []
        ENGINE._clamp_flow(vals, reasons, RULES["printers"]["A1mini"],
                           RULES["filaments"]["TPU"], warnings)
        cap = 6 / (0.3 * 0.6)
        for k in ("outer_wall_speed", "inner_wall_speed", "sparse_infill_speed"):
            self.assertLessEqual(vals[k], cap + 1e-6, k)
        self.assertTrue(any("体积流量" in w for w in warnings))
        self.assertTrue(reasons["outer_wall_speed"])

    def test_reasons_present(self):
        res = self._run("quality")
        changed = [r for r in res.rows if r.changed]
        self.assertTrue(changed)
        for r in changed:
            self.assertTrue(r.reason, f"{r.key} 没有改动原因")

    def test_soft_key_skipped_when_absent(self):
        """工程里没有的软参数（3mf 不存储 / 机型差异）不能被写进文件。"""
        settings = dict(self.proj.settings)
        settings.pop("friction_compensation", None)
        proj = threemf.ThreeMfProject.load(self.path)
        proj.settings = settings
        res = ENGINE.optimize(proj.settings, printer_key="X1C", filament_key="PLA",
                              nozzle=0.4, mode_key="balanced")
        self.assertNotIn("friction_compensation", res.write_values)
        row = next((r for r in res.rows if r.key == "friction_compensation"), None)
        if row is not None:
            self.assertFalse(row.will_write)
            self.assertTrue(row.skip_reason)

    def test_user_calibrated_values_preserved(self):
        """用户实测标定值（收缩补偿、耗材流量上限、AMS 槽位）不能被默认值覆盖。"""
        settings = dict(self.proj.settings)
        settings["counter_coef_1"] = '["-0.0001"]'
        settings["counter_limit_max"] = '["0.033"]'
        settings["filament_max_volumetric_speed"] = '["18", "15", "15"]'
        settings["support_filament"] = "0"
        proj = threemf.ThreeMfProject.load(self.path)
        proj.settings = settings
        res = ENGINE.optimize(proj.settings, printer_key="X1C", filament_key="PLA",
                              nozzle=0.4, mode_key="balanced")
        for key in ("counter_coef_1", "counter_limit_max",
                    "filament_max_volumetric_speed", "support_filament"):
            self.assertNotIn(key, res.write_values,
                             f"{key} 是用户标定值，不应被改写")

    def test_follow_semantics_keys_not_written(self):
        """官方语义为「跟随默认」的键（内壁/稀疏加速度）不能被写成绝对值。"""
        res = self._run("strength")
        for key in ("inner_wall_acceleration", "sparse_infill_acceleration"):
            row = next((r for r in res.rows if r.key == key), None)
            if row is None:
                continue
            self.assertFalse(row.changed, f"{key} 跟随语义被破坏了")


class TestThreeMfIO(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.src = build_sample(Path(self.td) / "orig.3mf", sliced=True)
        self.proj = threemf.ThreeMfProject.load(self.src)
        self.det = detector.detect(self.proj, RULES)
        self.res = ENGINE.optimize(self.proj.settings, printer_key=self.det.printer_key,
                                   filament_key=self.det.filament_key,
                                   nozzle=self.det.nozzle, mode_key="balanced")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_write_roundtrip(self):
        before = self.src.read_bytes()
        written, skipped = self.proj.apply(self.res.write_values)
        self.assertTrue(written)
        out = self.proj.save_as(Path(self.td) / "out.3mf")
        self.assertEqual(before, self.src.read_bytes(), "原文件被改动了")

        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            self.assertIn("3D/3dmodel.model", names)
            self.assertIn("Metadata/model_settings.config", names)
            self.assertNotIn("Metadata/slice_info.config", names)
            self.assertFalse(any(n.endswith(".gcode") for n in names))
            data = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
        for k, v in written.items():
            self.assertEqual(data[k], v, k)

        again = threemf.ThreeMfProject.load(out)
        self.assertEqual(again.settings["sparse_infill_pattern"], "gyroid")

    def test_refuse_overwrite_source(self):
        with self.assertRaises(threemf.ThreeMfError):
            self.proj.save_as(self.src)

    def test_reject_non_3mf(self):
        bad = Path(self.td) / "x.3mf"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(threemf.ThreeMfError):
            threemf.ThreeMfProject.load(bad)

    def test_reject_plain_model_3mf(self):
        p = Path(self.td) / "plain.3mf"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("3D/3dmodel.model", "<?xml version='1.0'?><model/>")
        with self.assertRaises(threemf.ThreeMfError):
            threemf.ThreeMfProject.load(p)


class TestReport(unittest.TestCase):
    def test_markdown_and_csv(self):
        with tempfile.TemporaryDirectory() as td:
            p = build_sample(Path(td) / "a.3mf")
            proj = threemf.ThreeMfProject.load(p)
            det = detector.detect(proj, RULES)
            res = ENGINE.optimize(proj.settings, printer_key=det.printer_key,
                                  filament_key=det.filament_key,
                                  nozzle=det.nozzle, mode_key="strength")
            md = report.build_markdown(str(p), det, res)
            self.assertIn("参数对比", md)
            self.assertIn("强度优先", md)
            self.assertIn("已知限制", md)
            csv_path = report.rows_to_csv(res.rows, Path(td) / "r.csv")
            text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("外壁速度", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
