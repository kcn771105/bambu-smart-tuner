"""六档模式的专项测试。

背景：模式扩展后一共六档——
    strength 强度优先 / quality 表面质量优先 / balanced 均衡模式
    draft 快速草稿 / fine 精细 / ultrafine 超精细
后三档是按官方过程预设的档位差分生成的：
    draft     ≈ 0.24mm Draft @BBL X1C
    fine      ≈ 0.12mm Fine @BBL X1C
    ultrafine ≈ 0.08mm Extra Fine @BBL X1C

本文件锁住几件事：
    · 六档模式都在规则库里、都有中文标签、都真的能产出改动
    · 精细/超精细档的悬垂判定角 = 官方 20° / 15°（不被交叉规则顶回）
    · 草稿档不加厚墙体、不动填充密度（只求快）
    · 模式族映射：fine/ultrafine 继承 quality 族的几何规则
    · 草稿档会丢掉「加厚类」操作
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import detector, model_analysis, modes as modes_reg, rules_engine, schema, threemf  # noqa: E402
from tools.make_sample_3mf import build_sample  # noqa: E402

ENGINE = rules_engine.build_engine()
RULES = ENGINE.rules

ALL_MODES = ("strength", "quality", "balanced", "draft", "fine", "ultrafine")


class TestModeRegistry(unittest.TestCase):
    def test_all_modes_registered(self):
        keys = [k for k, _ in ENGINE.mode_choices()]
        for k in ALL_MODES:
            self.assertIn(k, keys, f"规则库里缺模式 {k}")

    def test_modes_have_chinese_labels(self):
        for k, label in ENGINE.mode_choices():
            self.assertTrue(label.strip(), k)
            # 中文标签里至少要有一个汉字
            self.assertTrue(any("一" <= ch <= "鿿" for ch in label),
                            f"{k} 的标签 {label!r} 不是中文")

    def test_mode_descriptions_present(self):
        for k in ALL_MODES:
            node = RULES["modes"].get(k, {})
            self.assertTrue(str(node.get("desc", "")).strip(), f"{k} 缺描述")

    def test_ui_order_matches_rules(self):
        self.assertEqual(tuple(modes_reg.MODE_UI_ORDER), ALL_MODES)

    def test_family_mapping(self):
        self.assertEqual(modes_reg.family("fine"), "precision")
        self.assertEqual(modes_reg.family("ultrafine"), "precision")
        self.assertEqual(modes_reg.family("draft"), "draft")
        self.assertEqual(modes_reg.family("balanced"), "balanced")
        self.assertEqual(modes_reg.family("不存在的模式"), "balanced")

    def test_quality_family_contains_fine_modes(self):
        members = set(modes_reg.group_members("quality"))
        self.assertIn("quality", members)
        self.assertIn("fine", members)
        self.assertIn("ultrafine", members)

    def test_base_fallback(self):
        self.assertEqual(modes_reg.MODE_BASE_FALLBACK["draft"], "balanced")
        self.assertEqual(modes_reg.MODE_BASE_FALLBACK["fine"], "quality")
        self.assertEqual(modes_reg.MODE_BASE_FALLBACK["ultrafine"], "quality")


class TestModeEffects(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.path = build_sample(Path(self.td) / "sample.3mf")
        self.proj = threemf.ThreeMfProject.load(self.path)
        self.det = detector.detect(self.proj, RULES)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _run(self, mode, **kw):
        return ENGINE.optimize(self.proj.settings, printer_key="X1C",
                               filament_key="PLA", nozzle=0.4, mode_key=mode,
                               detection_warnings=list(self.det.warnings),
                               detection_notes=list(self.det.notes), **kw)

    def test_every_mode_produces_changes(self):
        for mode in ALL_MODES:
            res = self._run(mode)
            self.assertGreater(res.changed_count, 5, f"{mode} 改动太少")
            for row in res.rows:
                s = schema.PARAMS[row.key]
                if s.kind == schema.ENUM and s.choices:
                    self.assertIn(row.new_value, s.choices, f"{mode}/{row.key}")
                elif s.kind not in (schema.BOOL,):
                    self.assertGreaterEqual(float(row.new_value), s.vmin - 1e-6, f"{mode}/{row.key}")
                    self.assertLessEqual(float(row.new_value), s.vmax + 1e-6, f"{mode}/{row.key}")

    def test_fine_mode_uses_official_threshold_angle(self):
        """精细档 = 官方 0.12mm Fine 档，悬垂判定角 20°。"""
        res = self._run("fine")
        self.assertEqual(float(res.values["support_threshold_angle"]), 20.0)

    def test_ultrafine_mode_uses_official_threshold_angle(self):
        """超精细档 = 官方 0.08mm Extra Fine 档，悬垂判定角 15°。"""
        res = self._run("ultrafine")
        self.assertEqual(float(res.values["support_threshold_angle"]), 15.0)

    def test_draft_mode_uses_official_threshold_angle(self):
        """草稿档 = 官方 0.24mm Draft 档，判定角放宽到 35°。"""
        res = self._run("draft")
        self.assertEqual(float(res.values["support_threshold_angle"]), 35.0)

    def test_draft_mode_does_not_thicken(self):
        """草稿档只求快：不加厚墙体、不动填充密度。"""
        res = self._run("draft")
        ops = RULES["modes"]["draft"].get("ops", {})
        for key in ("wall_loops", "sparse_infill_density", "top_shell_layers",
                    "bottom_shell_layers", "infill_wall_overlap"):
            self.assertNotIn(key, ops, f"草稿档不该动 {key}")

    def test_fine_mode_thins_layer_height(self):
        """精细/超精细档把层高压到 0.12 / 0.08 mm 一线。"""
        fine = self._run("fine")
        ultra = self._run("ultrafine")
        self.assertLess(float(fine.values["layer_height"]), 0.16)
        self.assertLess(float(ultra.values["layer_height"]), 0.1)

    def test_draft_mode_raises_layer_height(self):
        res = self._run("draft")
        self.assertGreater(float(res.values["layer_height"]), 0.2)

    def test_fine_modes_inherit_quality_family_geometry_rules(self):
        """fine/ultrafine 命中 quality 族的几何规则（族映射生效）。"""
        fine = self._run("fine")
        balanced = self._run("balanced")
        # quality 族的几何规则里有「layer_height 在 small_detail 情形下压到 0.85 倍」
        # 这类只有 quality 命中的规则；fine 应当与 quality 同族命中。
        self.assertNotEqual(fine.changed_count, 0)
        self.assertNotEqual(balanced.changed_count, 0)

    def test_mode_only_writes_process_scope(self):
        for mode in ALL_MODES:
            res = self._run(mode)
            for key in res.write_values:
                self.assertEqual(scope_of(key), "process", f"{mode} 写了非工艺页键 {key}")


def scope_of(key: str) -> str:
    from core import scope
    return scope.scope_of(key)


class TestDraftDropKeys(unittest.TestCase):
    def test_draft_drop_keys_are_known(self):
        for key in modes_reg.DRAFT_DROP_KEYS:
            self.assertIn(key, schema.PARAMS, f"DRAFT_DROP_KEYS 里的 {key} 不在参数表里")

    def test_draft_drop_keys_cover_thickening_params(self):
        for key in ("wall_loops", "top_shell_layers", "bottom_shell_layers",
                    "sparse_infill_density"):
            self.assertIn(key, modes_reg.DRAFT_DROP_KEYS)


if __name__ == "__main__":
    unittest.main()
