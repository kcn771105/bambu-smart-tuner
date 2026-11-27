"""打印板同步的回归测试（板型 / 温度 / 板面 / 兼容性 / 模型放得下吗）。"""
from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from pathlib import Path

from core import plate, rules_engine

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "BambuRules.json"


def _rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))


class FakeProject:
    def __init__(self, settings: dict):
        self.settings = settings


def _base_settings(bed_type: str = "Supertack Plate",
                   cool: str = "0", eng: str = "70",
                   hot: str = "70", tex: str = "80",
                   tack: str = "60", area: str | None = None) -> dict:
    return {
        "curr_bed_type": bed_type,
        "cool_plate_temp": [cool],
        "eng_plate_temp": [eng],
        "hot_plate_temp": [hot],
        "textured_plate_temp": [tex],
        "supertack_plate_temp": [tack],
        "printable_area": area or '["0x0","256x0","256x256","0x256"]',
        "printable_height": "256",
        "wrapping_exclude_area": '["153x256","216x256","216x235","153x235"]',
    }


@dataclass
class FakeObj:
    size_x: float
    size_y: float


@dataclass
class FakeProfile:
    objects: list


class TestPlateRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = _rules()

    def test_read_bed_type_and_temp(self):
        proj = FakeProject(_base_settings("Supertack Plate"))
        info = plate.read(proj, self.rules)
        self.assertEqual(info.name, "Supertack Plate")
        self.assertEqual(info.temp_key, "supertack_plate_temp")
        self.assertAlmostEqual(info.temp, 60.0)
        self.assertTrue(info.supported)

    def test_read_bed_size(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        self.assertAlmostEqual(info.bed_w, 256.0)
        self.assertAlmostEqual(info.bed_d, 256.0)
        self.assertAlmostEqual(info.bed_h, 256.0)
        self.assertEqual(info.exclude_blocks, 1)     # 4 个角点 = 1 块

    def test_cool_plate_zero_means_unsupported(self):
        info = plate.read(FakeProject(_base_settings("Cool Plate", cool="0")), self.rules)
        self.assertEqual(info.temp_key, "cool_plate_temp")
        self.assertFalse(info.supported)

    def test_smooth_pei_is_high_temp_plate(self):
        """Studio 把「光滑 PEI」和「高温板」当同一格（官方 machine 预设写成
        `Smooth PEI Plate / High Temp Plate`），温度键是 hot_plate_temp。"""
        info = plate.read(FakeProject(_base_settings("Smooth PEI Plate")), self.rules)
        self.assertEqual(info.temp_key, "hot_plate_temp")

    def test_unknown_name_falls_back(self):
        info = plate.read(FakeProject(_base_settings("Some Future Plate")), self.rules)
        self.assertTrue(info.known)          # 有名字
        self.assertEqual(info.key, "Supertack Plate")   # 兜底到出厂默认

    def test_missing_settings_does_not_crash(self):
        info = plate.read({}, self.rules)
        self.assertFalse(info.known)


class TestPlateCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = _rules()

    def test_supported_plate_notes(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        warns, notes, ops = plate.check(info, rules=self.rules, printer_key="P2S",
                                        filament_key="PETG")
        self.assertEqual(warns, [])
        self.assertTrue(any("打印板已同步" in n for n in notes))
        self.assertIn("elefant_foot_compensation", ops)

    def test_unsupported_plate_warns(self):
        info = plate.read(FakeProject(_base_settings("Cool Plate", cool="0")), self.rules)
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="P2S",
                                    filament_key="PETG")
        self.assertTrue(any("打印板不兼容" in w for w in warns))

    def test_bed_size_mismatch_warns(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="A1mini",
                                    filament_key="PETG")
        self.assertTrue(any("板面尺寸与机型不符" in w for w in warns))

    def test_bed_size_match_no_warning(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="X1C",
                                    filament_key="PLA")
        self.assertFalse(any("板面尺寸" in w for w in warns))

    def test_model_too_big_warns(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        prof = FakeProfile(objects=[FakeObj(300.0, 120.0)])
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="P2S",
                                    filament_key="PETG", profile=prof)
        self.assertTrue(any("模型放不下" in w for w in warns))

    def test_model_rotated_still_fits(self):
        """H2D 板面 350×320：300×340 只有转 90° 才放得下。"""
        info = plate.read(FakeProject(_base_settings()), self.rules)
        prof = FakeProfile(objects=[FakeObj(300.0, 340.0)])
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="H2D",
                                    filament_key="PETG", profile=prof)
        self.assertFalse(any("模型放不下" in w for w in warns))

    def test_model_too_big_for_h2d_warns(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        prof = FakeProfile(objects=[FakeObj(330.0, 330.0)])   # 350×320 两个方向都放不下
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="H2D",
                                    filament_key="PETG", profile=prof)
        self.assertTrue(any("模型放不下" in w for w in warns))

    def test_small_bed_a1mini_rejects_256mm_part(self):
        info = plate.read(FakeProject(_base_settings()), self.rules)
        prof = FakeProfile(objects=[FakeObj(200.0, 200.0)])
        warns, _n, _o = plate.check(info, rules=self.rules, printer_key="A1mini",
                                    filament_key="PLA", profile=prof)
        self.assertTrue(any("模型放不下" in w for w in warns))


class TestPlateInRules(unittest.TestCase):
    def test_every_printer_has_bed(self):
        rules = _rules()
        for key, node in rules["printers"].items():
            with self.subTest(printer=key):
                bed = node.get("bed") or []
                self.assertEqual(len(bed), 3, f"{key} 缺 bed")
                self.assertGreater(bed[0], 0)

    def test_plate_process_keys_are_writable(self):
        """板层只能碰非 preserve 的键（preserve 的键引擎会静默跳过）。"""
        from core import schema

        rules = _rules()
        for key, node in (rules.get("plates") or {}).get("items", {}).items():
            for pkey in (node.get("process") or {}):
                with self.subTest(plate=key, param=pkey):
                    spec = schema.PARAMS.get(pkey)
                    self.assertIsNotNone(spec, f"{pkey} 不在 schema 里")
                    self.assertFalse(spec.preserve, f"{pkey} 是 preserve，板层改不动")


class TestEnginePlate(unittest.TestCase):
    def test_opt_result_carries_plate(self):
        rules = _rules()
        eng = rules_engine.RulesEngine(rules)
        settings = _base_settings()
        res = eng.optimize(settings, printer_key="P2S", filament_key="PETG",
                           nozzle=0.4, mode_key="balanced")
        self.assertIn("打印板", res.plate)
        self.assertTrue(any("打印板" in n for n in res.notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
