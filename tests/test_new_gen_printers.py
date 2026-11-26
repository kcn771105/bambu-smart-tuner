"""新版机型（Bambu Studio 2.09 新增 A2L / H2C / H3C / P3C / X2D）的回归测试。

真值来源：官方仓库 tag v02.09.02.62 的 machine 预设（沿 inherits 合并、取 0.4 喷嘴第 0 槽），
抓取脚本 tools/_fetch_official_machine.py。
"""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = json.load(io.open(ROOT / "rules" / "BambuRules.json", encoding="utf-8-sig"))

# 官方实测（0.4 喷嘴）：速度 / 加速度 / 空走加速度 / 熔池 / 热床
OFFICIAL = {
    "A2L": dict(speed=500, accel=12000, travel=9000, vol=92, bed=[330, 320, 325]),
    "H2C": dict(speed=1000, accel=20000, travel=9000, vol=130, bed=[330, 320, 325]),
    "H3C": dict(speed=1400, accel=25000, travel=9000, vol=125.9, bed=[330, 320, 325]),
    "P3C": dict(speed=1400, accel=25000, travel=9000, vol=125.9, bed=[256, 256, 260]),
    "X2D": dict(speed=1000, accel=20000, travel=9000, vol=92, bed=[256, 256, 261]),
}

# 官方 filament 预设 filament_max_volumetric_speed 第 0 槽
FLOW = {
    "A2L": {"PLA": 21, "PETG": 18, "ABS": 16, "ASA": 18, "TPU": 3.6},
    "H2C": {"PLA": 25, "PETG": 21, "ABS": 20, "ASA": 20, "TPU": 3.6},
    "H3C": {"PLA": 25, "PETG": 18, "ABS": 20, "ASA": 20, "TPU": 3.6},
    "P3C": {"PLA": 25, "PETG": 18, "ABS": 20, "ASA": 20, "TPU": 3.6},
    "X2D": {"PLA": 22, "PETG": 21, "ABS": 16, "ASA": 18, "TPU": 3.6},
}


class TestNewPrintersExist(unittest.TestCase):
    def test_all_five_present(self):
        for key in OFFICIAL:
            with self.subTest(key=key):
                self.assertIn(key, RULES["printers"])

    def test_limits_match_official(self):
        for key, want in OFFICIAL.items():
            with self.subTest(key=key):
                lim = RULES["printers"][key]["limits"]
                self.assertEqual(lim["max_speed"], want["speed"])
                self.assertEqual(lim["max_accel"], want["accel"])
                self.assertEqual(lim["max_travel_accel"], want["travel"])
                self.assertAlmostEqual(lim["nozzle_volume"], want["vol"], places=1)

    def test_bed_matches_official(self):
        for key, want in OFFICIAL.items():
            with self.subTest(key=key):
                self.assertEqual(RULES["printers"][key]["bed"], want["bed"])

    def test_every_printer_has_bed_and_limits(self):
        for key, node in RULES["printers"].items():
            with self.subTest(key=key):
                self.assertEqual(len(node.get("bed") or []), 3)
                lim = node.get("limits") or {}
                for f in ("max_speed", "max_accel", "max_travel_accel",
                          "min_layer_height", "max_layer_height", "nozzle_volume"):
                    self.assertIn(f, lim)

    def test_aliases_cover_printer_model_string(self):
        """工程里的 printer_model 是「Bambu Lab X2D」这种全称，必须能被别名命中。"""
        for key in OFFICIAL:
            with self.subTest(key=key):
                node = RULES["printers"][key]
                self.assertIn(node["label"], node["aliases"])


class TestNewPrinterFlow(unittest.TestCase):
    def test_flow_by_printer_complete(self):
        for fkey, fnode in RULES["filaments"].items():
            if fkey == "GENERIC":
                # GENERIC 是「认不出耗材时的兜底」，故意不分机型（统一 8 mm³/s）
                continue
            fb = (fnode.get("limits") or {}).get("flow_by_printer") or {}
            for key in OFFICIAL:
                with self.subTest(filament=fkey, printer=key):
                    self.assertIn(key, fb, f"耗材 {fkey} 缺机型 {key} 的流量标定")

    def test_flow_values_match_official(self):
        for key, mats in FLOW.items():
            for fkey, want in mats.items():
                node = RULES["filaments"].get(fkey)
                if node is None:
                    # 规则库耗材键是 PLA/PETG/ABS/ASA/TPU
                    continue
                with self.subTest(printer=key, filament=fkey):
                    got = node["limits"]["flow_by_printer"][key]
                    self.assertAlmostEqual(float(got), float(want), places=2)

    def test_nozzle_flow_groups_cover_new_groups(self):
        groups = RULES["nozzle_flow"]["by_group"]
        for grp in ("A2", "H3", "P3", "X2"):
            with self.subTest(group=grp):
                self.assertIn(grp, groups)
                for mat in ("PLA", "PETG", "ABS", "ASA", "TPU"):
                    self.assertIn(mat, groups[grp])
                    self.assertEqual(len(groups[grp][mat]), 4)


class TestNewPrinterOptimize(unittest.TestCase):
    """端到端：每个新机型都要能跑完整条优化链，不抛异常、不写越界值。"""

    def test_optimize_each_new_printer(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from core import rules_engine, schema

        engine = rules_engine.RulesEngine(RULES)
        current = {"layer_height": "0.2", "wall_loops": "2", "sparse_infill_density": "15%",
                   "outer_wall_speed": "200", "inner_wall_speed": "300"}
        for key in OFFICIAL:
            for mode in ("balanced", "strength", "quality"):
                with self.subTest(printer=key, mode=mode):
                    res = engine.optimize(current, printer_key=key, filament_key="PLA",
                                          nozzle=0.4, mode_key=mode)
                    self.assertGreater(len(res.rows), 0)
                    for k, v in res.write_values.items():
                        spec = schema.PARAMS.get(k)
                        if spec is None:
                            continue
                        if spec.kind in (schema.ENUM, schema.BOOL, schema.ENUM_ARRAY):
                            continue      # 枚举/布尔不按数值比上下限
                        self.assertTrue(spec.vmin <= float(str(v).rstrip('%')) <= spec.vmax,
                                        f"{key}/{mode}: {k}={v} 越界")


if __name__ == "__main__":
    unittest.main()
