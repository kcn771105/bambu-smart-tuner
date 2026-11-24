"""喷嘴流量同步的回归测试。

背景：官方 `filament_max_volumetric_speed` 是按喷嘴给的
（PETG 在 X1C 上 0.2→1、0.4→13、0.8→16）。换喷嘴不同步流量，
0.2 喷嘴会按 0.4 的流量算速度 —— 物理跑不到，轻则糊面重则堵料。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import nozzle_flow, rules_engine

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "BambuRules.json"


class TestNozzleFlowTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))

    def test_table_present(self):
        node = self.rules.get("nozzle_flow") or {}
        self.assertIn("by_group", node)
        self.assertGreaterEqual(len(node["by_group"]), 5)
        for group, fams in node["by_group"].items():
            with self.subTest(group=group):
                self.assertIn("PETG", fams)
                self.assertEqual(sorted(fams["PETG"].keys()),
                                 ["0.2", "0.4", "0.6", "0.8"])

    def test_official_values_match_bambu(self):
        """人工从官方预设抄下来的这组值不能被误改。"""
        cases = [
            ("X1", "PETG", 0.2, 1), ("X1", "PETG", 0.4, 13),
            ("X1", "PETG", 0.8, 16), ("X1", "PLA", 0.4, 21),
            ("A1", "PETG", 0.4, 9), ("H2", "PLA", 0.4, 25),
            ("H2", "ABS", 0.6, 25), ("P2", "ASA", 0.4, 18),
        ]
        for group, fam, noz, want in cases:
            with self.subTest(group=group, fam=fam, noz=noz):
                val, _ = nozzle_flow.limit(self.rules, group=group,
                                           filament_key=fam, nozzle=noz)
                self.assertAlmostEqual(val, float(want))

    def test_tpu_is_nozzle_independent(self):
        for noz in (0.2, 0.4, 0.6, 0.8):
            with self.subTest(noz=noz):
                val, _ = nozzle_flow.limit(self.rules, group="X1",
                                           filament_key="TPU", nozzle=noz)
                self.assertAlmostEqual(val, 3.6)

    def test_smaller_nozzle_means_less_flow(self):
        prev = None
        for noz in (0.2, 0.4, 0.6, 0.8):
            val, _ = nozzle_flow.limit(self.rules, group="X1",
                                       filament_key="PETG", nozzle=noz)
            if prev is not None:
                self.assertGreaterEqual(val, prev)
            prev = val

    def test_snap_nozzle(self):
        self.assertEqual(nozzle_flow.snap_nozzle(0.25), 0.2)
        self.assertEqual(nozzle_flow.snap_nozzle(0.45), 0.4)
        self.assertEqual(nozzle_flow.snap_nozzle(0.65), 0.6)
        self.assertEqual(nozzle_flow.snap_nozzle(1.0), 0.8)
        self.assertIsNone(nozzle_flow.snap_nozzle(None))
        self.assertIsNone(nozzle_flow.snap_nozzle(0))

    def test_ratio_between_nozzles(self):
        r, src = nozzle_flow.ratio(self.rules, group="X1", filament_key="PETG",
                                   from_nozzle=0.4, to_nozzle=0.2)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r, 1 / 13)
        self.assertIn("13", src)


class TestEngineFlowFollowsNozzle(unittest.TestCase):
    """换喷嘴时引擎实际采用的流量上限必须跟着变。"""

    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))

    def _run(self, nozzle: float, project_nozzle: float, project_flow: float,
             printer: str = "X1C", filament: str = "PETG"):
        eng = rules_engine.RulesEngine(self.rules)
        hw = __import__("core.hardware", fromlist=["HardwareInfo"]).HardwareInfo(
            from_project=True, nozzle_diameter=project_nozzle,
            max_volumetric_speed=project_flow)
        res = eng.optimize({}, printer_key=printer, filament_key=filament,
                           nozzle=nozzle, mode_key="balanced",
                           hardware_info=hw, nozzle_explicit=True)
        return res, eng

    def test_same_nozzle_keeps_project_value(self):
        res, eng = self._run(0.4, 0.4, 18.0)
        self.assertAlmostEqual(eng._flow_limit, 18.0)
        self.assertTrue(any("喷嘴同步" in w for w in res.warnings) is False)

    def test_02_nozzle_clamps_to_one(self):
        res, eng = self._run(0.2, 0.4, 18.0)
        self.assertAlmostEqual(eng._flow_limit, 1.0)
        self.assertTrue(any("喷嘴同步" in w for w in res.warnings))
        self.assertAlmostEqual(res.flow_limit, 1.0)

    def test_08_nozzle_allows_more_than_02(self):
        _, eng02 = self._run(0.2, 0.4, 18.0)
        _, eng08 = self._run(0.8, 0.4, 18.0)
        self.assertGreater(eng08._flow_limit, eng02._flow_limit)

    def test_never_exceeds_official_for_new_nozzle(self):
        """换了喷嘴就必须受新喷嘴的官方上限约束（同喷嘴时工程标定值优先，不在此列）。"""
        for noz in (0.2, 0.6, 0.8):
            with self.subTest(noz=noz):
                _, eng = self._run(noz, 0.4, 18.0)
                official, _ = nozzle_flow.limit(
                    self.rules, group="X1", filament_key="PETG", nozzle=noz)
                self.assertLessEqual(eng._flow_limit, official + 1e-6)

    def test_speeds_respect_flow_after_nozzle_change(self):
        """0.2 喷嘴下内壁速度必须被压到流量允许的范围。"""
        res, eng = self._run(0.2, 0.4, 18.0)
        lh = float(res.values["layer_height"])
        lw = float(res.values["inner_wall_line_width"])
        cap = eng._flow_limit / (lh * lw)
        self.assertLessEqual(float(res.values["inner_wall_speed"]), cap + 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
