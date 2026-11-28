"""Studio 参数位置对照表 + 报告定位的测试。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, report, rules_engine, scope, studio_ui  # noqa: E402
from core.threemf import ThreeMfProject  # noqa: E402

from tests._sample import PROJ as _SAMPLE  # noqa: E402
PROJ = str(_SAMPLE)
PROCESS_KEYS = [k for k, v in scope.SCOPE.items() if v == scope.PROCESS]


class TestStudioUiData(unittest.TestCase):
    def test_data_loaded(self):
        self.assertGreater(studio_ui.available(), 200)

    def test_every_process_key_has_entry(self):
        miss = [k for k in PROCESS_KEYS if studio_ui.info(k).path.strip() == ""]
        self.assertEqual(miss, [])

    def test_known_keys_have_tab_and_hint(self):
        for key, tab in [("layer_height", "质量"), ("wall_loops", "强度"),
                         ("outer_wall_speed", "速度"), ("brim_width", "多材料"),
                         ("support_base_pattern_spacing", "支撑")]:
            spot = studio_ui.info(key)
            self.assertEqual(spot.tab, tab, f"{key} 页签不对：{spot.tab}")
            self.assertTrue(spot.search_hint, f"{key} 没有搜索词")

    def test_hidden_keys_say_so(self):
        for key in ("conformal_infill", "interlocking_beam", "accel_to_decel_enable"):
            spot = studio_ui.info(key)
            self.assertTrue(spot.hidden, f"{key} 应该标成界面没有")
            self.assertIn("界面没有", spot.path)
            self.assertEqual(spot.search_hint, "")

    def test_path_never_empty(self):
        for k in PROCESS_KEYS:
            self.assertTrue(studio_ui.info(k).path.strip(), k)

    def test_group_shown_when_known(self):
        self.assertEqual(studio_ui.info("wall_loops").path, "强度 › 墙层数")
        self.assertEqual(studio_ui.info("layer_height").path, "质量 › 层高")


class TestReportShowsStudioSpot(unittest.TestCase):
    def test_report_table_has_studio_column(self):
        proj = ThreeMfProject.load(PROJ)
        eng = rules_engine.build_engine()
        det = detector.detect(proj, eng.rules)
        res = eng.optimize(proj.settings, printer_key="P2S", filament_key="PETG",
                           nozzle=0.4, mode_key="balanced")
        text = report.build_markdown(PROJ, det, res)
        self.assertIn("| 参数 | Studio 里在哪 |", text)
        self.assertTrue(any(x in text for x in ("质量 ›", "速度 ›", "强度 ›", "多材料 ›", "支撑 ›")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
