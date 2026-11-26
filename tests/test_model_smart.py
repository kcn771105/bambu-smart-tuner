"""按模型实测做的「针对性」判断：悬垂跨度、悬垂高度分布、站不站得稳。

这一组测的不是「参数给得对不对」，而是**两个不同的件必须得到不同的参数**：
如果换一个模型结果一模一样，那这些规则就没在工作。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from core import detector, hardware, model_analysis, rules_engine, support_model
from core.threemf import ThreeMfProject

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RULES = ROOT / "rules" / "BambuRules.json"

PLATE = ROOT / "samples" / "shape_plate_flat.3mf"          # 扁平板：无悬垂
TOWER = ROOT / "samples" / "shape_tower_overhang.3mf"      # 悬垂塔：上部一大片悬空


def _run(path: Path):
    eng = rules_engine.build_engine(str(RULES))
    proj = ThreeMfProject.load(str(path))
    det = detector.detect(proj, eng.rules)
    prof = model_analysis.analyse(proj)
    res = eng.optimize(
        proj.settings, printer_key=det.printer_key, filament_key=det.filament_key,
        nozzle=det.nozzle, mode_key="balanced", model_profile=prof,
        hardware_info=hardware.read(proj), seam_smooth=True)
    return proj, prof, res


def _val(res, key):
    raw = res.write_values.get(key)
    if raw is None:
        return None
    return str(raw).strip('[]"').split(",")[0].strip('"').strip()


class TestMeasuredSignals(unittest.TestCase):
    """几何量本身要能分出「有悬垂」和「没悬垂」。"""

    def test_tower_has_overhang_plate_has_none(self):
        _p1, tower, _r1 = _run(TOWER)
        _p2, plate, _r2 = _run(PLATE)
        self.assertGreater(tower.support_ratio, 0.03, "悬垂塔测不出悬垂")
        self.assertLess(plate.support_ratio, 0.005, "平板被测出悬垂，说明方向判反了")

    def test_bridge_span_only_on_overhang(self):
        """最长悬垂边：塔有几十毫米，平板是 0（平板没有朝下的面）。"""
        _p1, tower, _r1 = _run(TOWER)
        _p2, plate, _r2 = _run(PLATE)
        self.assertGreater(tower.max_bridge_span, 20.0)
        self.assertEqual(plate.max_bridge_span, 0.0)

    def test_overhang_position_is_measured(self):
        """塔的悬垂全长在上部，top_ratio 要接近 1；平板没有悬垂 → 0。"""
        _p1, tower, _r1 = _run(TOWER)
        _p2, plate, _r2 = _run(PLATE)
        self.assertGreater(tower.overhang_top_ratio, 0.6)
        self.assertEqual(plate.overhang_top_ratio, 0.0)


class TestBridgeRule(unittest.TestCase):
    """跨度够大 → 桥接速度必须被压下来；没有悬垂的件不许动它。"""

    def test_tower_bridge_speed_capped(self):
        _p, _prof, res = _run(TOWER)
        self.assertEqual(_val(res, "bridge_speed"), "30")

    def test_plate_keeps_bridge_speed(self):
        _p, _prof, res = _run(PLATE)
        self.assertNotIn("bridge_speed", res.write_values)

    def test_row_explains_the_number(self):
        _p, _prof, res = _run(TOWER)
        rows = [d for d in res.derivations if "悬垂跨度" in d.get("metric", "")]
        self.assertTrue(rows, "推导表里没有悬垂跨度这一行")
        self.assertIn("mm", rows[0]["measured"])


class TestStabilityRule(unittest.TestCase):
    """细高 + 脚小 → 加宽裙边、首层降速。"""

    def test_tower_gets_wider_brim(self):
        _p, prof, res = _run(TOWER)
        self.assertGreaterEqual(prof.slender, 3.0)
        self.assertEqual(_val(res, "brim_type"), "outer_only")
        self.assertEqual(_val(res, "initial_layer_speed"), "40")

    def test_flat_plate_not_treated_as_tall(self):
        _p, prof, res = _run(PLATE)
        self.assertLess(prof.slender, 1.0)
        self.assertNotEqual(_val(res, "initial_layer_speed"), "40")


class TestAutoSupport(unittest.TestCase):
    """自动档：有悬垂就该开支撑，没悬垂就别乱开。"""

    def test_tower_support_turned_on(self):
        _p, _prof, res = _run(TOWER)
        self.assertEqual(_val(res, "enable_support"), "1")
        self.assertTrue(any("支撑" in w and "悬垂" in w for w in res.warnings),
                        "自动开支撑时没有提示用户去核落点")

    def test_plate_support_stays_off(self):
        _p, _prof, res = _run(PLATE)
        self.assertNotEqual(_val(res, "enable_support"), "1")

    def test_top_heavy_overhang_gets_extra_interface_layer(self):
        """上部悬垂下面没东西托，接触面要比下部悬垂多一层。"""
        _p, prof, res = _run(TOWER)
        layers = int(float(_val(res, "support_interface_top_layers") or 0))
        self.assertGreaterEqual(layers, 3)
        self.assertGreaterEqual(prof.overhang_top_ratio, 0.6)

    def test_forced_off_wins(self):
        """用户在下拉里选「强制关闭」，几何判断不许把支撑又打开。"""
        eng = rules_engine.build_engine(str(RULES))
        proj = ThreeMfProject.load(str(TOWER))
        det = detector.detect(proj, eng.rules)
        prof = model_analysis.analyse(proj)
        res = eng.optimize(
            proj.settings, printer_key=det.printer_key, filament_key=det.filament_key,
            nozzle=det.nozzle, mode_key="balanced", model_profile=prof,
            hardware_info=hardware.read(proj), seam_smooth=True, support_mode="off")
        self.assertNotEqual(_val(res, "enable_support"), "1")


class TestSupportWhitelist(unittest.TestCase):
    """支撑键在「被裁过的工程」里也要能写进去，否则调了半天没生效。"""

    def test_support_keys_declared(self):
        for key in ("enable_support", "support_base_pattern_spacing",
                    "support_top_z_distance", "support_interface_top_layers"):
            self.assertIn(key, support_model.SUPPORT_KEYS)


if __name__ == "__main__":
    unittest.main()
