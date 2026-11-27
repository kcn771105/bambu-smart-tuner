"""本机 Studio 兼容层：板型/机型/版本对照，以及「换板不改温度」。

这一组用例全部不依赖本机真的装了 Studio —— 用假的 StudioEnv 顶替，
测的是判断逻辑本身；`studio_env.detect()` 只在真机上才有意义。
"""
from __future__ import annotations

import unittest

from core import studio_env, thermal


class TestCompareVersions(unittest.TestCase):
    def test_numeric_segments_not_strings(self):
        # 字符串比大小会把 "02.08" 排到 "02.03" 后面（对的），但 "1.10" < "1.9" 会错
        self.assertGreater(studio_env.compare_versions("1.10", "1.9"), 0)
        self.assertLess(studio_env.compare_versions("02.03.00.02", "02.08.04.57"), 0)
        self.assertEqual(studio_env.compare_versions("2.0", "2.0.0"), 0)

    def test_bad_input_is_neutral(self):
        # 有一边读不到就「不作判断」，别凭空报「你的文件更新」
        self.assertEqual(studio_env.compare_versions("", ""), 0)
        self.assertEqual(studio_env.compare_versions("1.0", ""), 0)


class TestStudioEnvCapabilities(unittest.TestCase):
    def _env(self, plates=("Textured PEI Plate", "Cool Plate"),
             machines=("Bambu Lab P2S",), version="02.03.00.02"):
        return studio_env.StudioEnv(found=True, root="C:/x", version=version,
                                    plates=tuple(plates), machines=tuple(machines))

    def test_supports_plate_variants(self):
        env = self._env()
        self.assertTrue(env.supports_plate("Textured PEI Plate"))
        self.assertTrue(env.supports_plate("纹理PEI打印板"), "中文名也该认")
        self.assertFalse(env.supports_plate("Supertack Plate"))

    def test_supports_machine(self):
        env = self._env()
        self.assertTrue(env.supports_machine("Bambu Lab P2S"))
        self.assertTrue(env.supports_machine("P2S"), "裸机型名也该认")
        self.assertFalse(env.supports_machine("Bambu Lab H2D"))


class TestCompatReport(unittest.TestCase):
    def _env(self, plates=("Textured PEI Plate", "Cool Plate")):
        return studio_env.StudioEnv(found=True, root="C:/x", version="02.03.00.02",
                                    plates=tuple(plates),
                                    machines=("Bambu Lab P2S",))

    def test_flags_unknown_plate(self):
        settings = {"curr_bed_type": "Supertack Plate", "printer_model": "Bambu Lab P2S",
                    "version": "02.08.04.57"}
        rep = studio_env.compat_report(settings, self._env())
        self.assertFalse(rep["plate_ok"])
        self.assertTrue(rep["project_newer"], "工程 02.08 比本机 02.03 新，要报出来")
        self.assertTrue(rep["machine_ok"])
        self.assertTrue(any("Supertack" in w or "板" in w for w in rep["warnings"]))

    def test_ok_when_everything_known(self):
        settings = {"curr_bed_type": "Textured PEI Plate",
                    "printer_model": "Bambu Lab P2S", "version": "02.03.00.02"}
        rep = studio_env.compat_report(settings, self._env(), chosen_plate="Textured PEI Plate")
        self.assertTrue(rep["plate_ok"])
        self.assertFalse(rep["project_newer"])
        self.assertEqual(rep["warnings"], [])

    def test_not_found_is_not_an_error(self):
        rep = studio_env.compat_report({"curr_bed_type": "Supertack Plate"},
                                       studio_env.StudioEnv())
        self.assertFalse(rep["studio_found"])


class TestReadBedTemp(unittest.TestCase):
    def test_reads_first_slot_of_json_array(self):
        settings = {"curr_bed_type": "Supertack Plate",
                    "supertack_plate_temp": '["60", "65"]'}
        self.assertEqual(thermal.read_bed_temp(settings), 60.0)

    def test_falls_back_to_initial_layer(self):
        settings = {"curr_bed_type": "Supertack Plate",
                    "supertack_plate_temp": '["0"]',
                    "supertack_plate_temp_initial_layer": '["65"]'}
        self.assertEqual(thermal.read_bed_temp(settings), 65.0)

    def test_none_when_nothing_usable(self):
        self.assertIsNone(thermal.read_bed_temp({"curr_bed_type": "Supertack Plate"}))


class TestBedKeepTemp(unittest.TestCase):
    """换板子时温度必须沿用原值 —— 这是「导入后板温自己变了」的防线。"""

    def setUp(self):
        self.rules = thermal.load_rules("rules/BambuRules.json") \
            if hasattr(thermal, "load_rules") else None
        if self.rules is None:
            from core import rules_engine
            self.rules = rules_engine.load_rules("rules/BambuRules.json")

    def _derive(self, **kw):
        return thermal.derive(self.rules, {"supertack_plate_temp": '["60"]'},
                              filament_key="PETG", printer_key="P2S", **kw)

    def test_baseline_differs_between_plates(self):
        base = self._derive(bed_type="Supertack Plate")     # PETG 70
        other = self._derive(bed_type="Cool Plate")         # PETG 30
        self.assertNotEqual(base.ops.get("supertack_plate_temp"),
                            other.ops.get("cool_plate_temp"))

    def test_keep_temp_wins_over_new_plate_baseline(self):
        out = self._derive(bed_type="Textured PEI Plate", bed_keep_temp=60.0)
        target = out.ops["textured_plate_temp"]
        target = target.get("set", target) if isinstance(target, dict) else target
        self.assertAlmostEqual(float(target), 60.0, places=3)
        self.assertTrue(any("以你原来的" in n or "为基准" in n for n in out.notes),
                        f"应当说明沿用了原板温，实际 notes={out.notes}")


if __name__ == "__main__":
    unittest.main()
