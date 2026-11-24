"""形状层 op 合并 + 支撑策略的回归测试。

覆盖三个缺陷的修法：

    1) core/shape_rules.py 的 _merge_op —— 异型合并必须保留双方语义
       （形状原型给的 {"max": 42} 与几何算出的 {"set": 38} 合并后不能丢 set）。
    2) core/support_plan.py 的 decide() —— 必须尊重用户工程里自己设的
       support_threshold_angle（判定角）与 enable_support（支撑开关）。
    3) core/support_plan.py 的 decide()/plan() —— 没有模型画像时
       （has_model=False）不能产出任何会改动 enable_support 的 op。

运行：python -m pytest tests/test_shape_support.py -q
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from core import model_analysis, support_plan, threemf      # noqa: E402
from core import shape_rules                               # noqa: E402
from make_shape_samples import SHAPES, build as build_shape  # noqa: E402


def _profile_from_shape(stem: str, td: Path) -> model_analysis.ModelProfile:
    """用 tools/make_shape_samples.py 的形状夹具算一份 ModelProfile。"""
    geom = SHAPES[stem][0]
    path = build_shape(td / f"{stem}.3mf", geom, stem)
    project = threemf.ThreeMfProject.load(path)
    return model_analysis.analyse(project)


def _heavy_profile() -> model_analysis.ModelProfile:
    """造一份悬垂很重的画像（不依赖夹具文件，纯内存构造）。"""
    heavy = model_analysis.ObjectProfile(
        oid="1", index=0, size_x=40, size_y=40, size_z=40,
        min_z=0, max_z=40, volume=64_000, surface=9_600, overhang_area=6_000)
    return model_analysis.ModelProfile(
        objects=[heavy], triangles=12, size_x=40, size_y=40, size_z=40,
        volume=heavy.volume, surface=heavy.surface,
        overhang_area=heavy.overhang_area, footprint=1_600)


def _light_profile() -> model_analysis.ModelProfile:
    """造一份悬垂很少的画像（扁平板）。"""
    light = model_analysis.ObjectProfile(
        oid="1", index=0, size_x=160, size_y=120, size_z=8,
        min_z=0, max_z=8, volume=153_600, surface=52_000, overhang_area=1_000)
    return model_analysis.ModelProfile(
        objects=[light], triangles=12, size_x=160, size_y=120, size_z=8,
        volume=light.volume, surface=light.surface,
        overhang_area=light.overhang_area, footprint=19_200)


# ================================================================== 1）op 合并

class TestMergeOp(unittest.TestCase):
    """core/shape_rules.py：异型合并保留双方语义，同型合并取更保守的一侧。"""

    def test_merge_set_and_max_keeps_both(self):
        """set + max → 两条约束都在（几何算出的角度不会被原型吃掉）。"""
        merged = shape_rules._merge_op({"max": 42}, {"set": 38})
        self.assertIn("set", merged)
        self.assertIn("max", merged)
        self.assertEqual(merged["set"], 38)
        self.assertEqual(merged["max"], 42)

    def test_merge_set_and_min_keeps_both(self):
        """set + min → 两条约束都在。"""
        merged = shape_rules._merge_op({"min": 20}, {"set": 35})
        self.assertEqual(merged.get("set"), 35)
        self.assertEqual(merged.get("min"), 20)

    def test_merge_set_and_mul_keeps_both(self):
        """set + mul → 两条约束都在（引擎在 set 出来的值上再乘）。"""
        merged = shape_rules._merge_op({"set": 2.0}, {"mul": 1.5})
        self.assertEqual(merged.get("set"), 2.0)
        self.assertEqual(merged.get("mul"), 1.5)

    def test_merge_set_and_add_keeps_both(self):
        """set + add → 两条约束都在。"""
        merged = shape_rules._merge_op({"set": 0.2}, {"add": 0.05})
        self.assertEqual(merged.get("set"), 0.2)
        self.assertEqual(merged.get("add"), 0.05)

    def test_merge_min_and_max_keeps_interval(self):
        """min + max → 区间（两条都在）。"""
        merged = shape_rules._merge_op({"min": 25}, {"max": 42})
        self.assertEqual(merged.get("min"), 25)
        self.assertEqual(merged.get("max"), 42)

    def test_merge_mul_with_bounds_keeps_all_keys(self):
        """mul + min/max/add → 全部键都在。"""
        merged = shape_rules._merge_op({"mul": 0.9}, {"max": 42})
        self.assertEqual(merged.get("mul"), 0.9)
        self.assertEqual(merged.get("max"), 42)
        merged = shape_rules._merge_op({"mul": 0.9}, {"min": 25})
        self.assertEqual(merged.get("mul"), 0.9)
        self.assertEqual(merged.get("min"), 25)
        merged = shape_rules._merge_op({"mul": 0.9}, {"add": 1.0})
        self.assertEqual(merged.get("mul"), 0.9)
        self.assertEqual(merged.get("add"), 1.0)

    def test_merge_same_type_keeps_conservative_side(self):
        """同型合并：mul 累乘、min 取大、max 取小、add 取大。"""
        self.assertAlmostEqual(shape_rules._merge_op({"mul": 0.9}, {"mul": 1.1})["mul"], 0.99)
        self.assertEqual(shape_rules._merge_op({"min": 20}, {"min": 30})["min"], 30)
        self.assertEqual(shape_rules._merge_op({"max": 45}, {"max": 38})["max"], 38)
        self.assertEqual(shape_rules._merge_op({"add": 0.1}, {"add": 0.2})["add"], 0.2)

    def test_merge_set_and_set_keeps_conservative(self):
        """set + set：数值型取较小（保守），布尔/枚举保持先出现的那条。"""
        self.assertEqual(shape_rules._merge_op({"set": 42}, {"set": 38})["set"], 38)
        self.assertEqual(shape_rules._merge_op({"set": True}, {"set": False})["set"], True)
        self.assertEqual(shape_rules._merge_op({"set": "tree(auto)"},
                                               {"set": "normal(auto)"})["set"], "tree(auto)")

    def test_merge_never_drops_existing_keys(self):
        """合并时不许丢任何原本存在的 op 键。"""
        a = {"set": 38, "max": 42}
        b = {"set": 38, "min": 25, "mul": 0.9}
        merged = shape_rules._merge_op(a, b)
        for key in ("set", "max", "min", "mul"):
            self.assertIn(key, merged, f"{key} 被合并丢了")

    def test_merge_empty_side(self):
        """空的一侧直接取另一侧。"""
        self.assertEqual(shape_rules._merge_op({}, {"set": 38}), {"set": 38})
        self.assertEqual(shape_rules._merge_op({"set": 38}, {}), {"set": 38})


# ================================================================== 2）用户判定角

class TestUserThresholdAngle(unittest.TestCase):
    """decide()：尊重用户在工程里自己设的 support_threshold_angle。"""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)

    def test_user_angle_smaller_is_used(self):
        """用户角比几何建议小 → 采用用户角（更早触发支撑，更安全）。"""
        profile = _heavy_profile()
        base = support_plan.decide(profile, mode="balanced")
        geo_angle = base.ops["support_threshold_angle"]["set"]
        user_angle = geo_angle - 10.0
        decision = support_plan.decide(profile, mode="balanced",
                                       user_threshold_angle=user_angle)
        self.assertEqual(decision.ops["support_threshold_angle"]["set"], user_angle)
        self.assertTrue(any("你把判定角设为" in r for r in decision.reasons),
                        decision.reasons)

    def test_user_angle_larger_uses_geometry_angle(self):
        """用户角比几何建议大 → 采用几何角，并写明取舍。"""
        profile = _heavy_profile()
        base = support_plan.decide(profile, mode="balanced")
        geo_angle = base.ops["support_threshold_angle"]["set"]
        decision = support_plan.decide(profile, mode="balanced",
                                       user_threshold_angle=geo_angle + 10.0)
        self.assertEqual(decision.ops["support_threshold_angle"]["set"], geo_angle)
        reasons = " ".join(decision.reasons)
        self.assertIn("你把判定角设为", reasons)
        self.assertIn("更贴合本模型", reasons)

    def test_user_angle_equal_geometry_keeps_value(self):
        """用户角与几何建议相同 → 取同一个值，不写多余的取舍说明。"""
        profile = _heavy_profile()
        base = support_plan.decide(profile, mode="balanced")
        geo_angle = base.ops["support_threshold_angle"]["set"]
        decision = support_plan.decide(profile, mode="balanced",
                                       user_threshold_angle=geo_angle)
        self.assertEqual(decision.ops["support_threshold_angle"]["set"], geo_angle)
        self.assertFalse(any("你把判定角设为" in r for r in decision.reasons))

    def test_smaller_user_angle_makes_support_more_likely(self):
        """用户角更小 → 触发门槛更低 → 更容易判定为需要支撑。"""
        # 悬垂占比 4.5%：落在默认门槛 6% 与更敏感门槛 3% 之间
        obj = model_analysis.ObjectProfile(
            oid="1", index=0, size_x=50, size_y=50, size_z=40,
            min_z=0, max_z=40, volume=100_000, surface=20_000, overhang_area=900)
        profile = model_analysis.ModelProfile(
            objects=[obj], triangles=12, size_x=50, size_y=50, size_z=40,
            volume=obj.volume, surface=obj.surface,
            overhang_area=obj.overhang_area, footprint=2_500)
        base = support_plan.decide(profile, mode="balanced")
        self.assertFalse(base.enable, "默认判定角下应当不触发支撑")
        self.assertEqual(base.ops.get("enable_support"), {"set": False})
        decision = support_plan.decide(profile, mode="balanced",
                                       user_threshold_angle=20.0)
        self.assertTrue(decision.enable, "用户角更敏感时应当触发支撑")
        self.assertNotIn("enable_support", decision.ops)


# ================================================================== 3）用户的支撑开关

class TestUserEnableSupport(unittest.TestCase):
    """decide()：不能把用户手动设的支撑开关静默翻掉。"""

    def test_user_enabled_support_is_kept(self):
        """用户开着支撑 + 几何上不需要 → 不产出关闭的 op，只写说明。"""
        profile = _light_profile()
        decision = support_plan.decide(profile, mode="balanced",
                                       user_enable_support=True)
        self.assertNotIn("enable_support", decision.ops)
        self.assertTrue(any("已保留原设置" in r for r in decision.reasons),
                        decision.reasons)

    def test_user_disabled_support_still_writes_false(self):
        """用户本来就是关的 → 照常写 enable_support=False。"""
        profile = _light_profile()
        decision = support_plan.decide(profile, mode="balanced",
                                       user_enable_support=False)
        self.assertEqual(decision.ops.get("enable_support"), {"set": False})

    def test_unknown_user_value_uses_geometry_conclusion(self):
        """工程里没有这个值（None）→ 按几何结论写。"""
        profile = _light_profile()
        decision = support_plan.decide(profile, mode="balanced",
                                       user_enable_support=None)
        self.assertEqual(decision.ops.get("enable_support"), {"set": False})


# ================================================================== 4）没有模型画像

class TestNoModel(unittest.TestCase):
    """has_model=False：不产出任何会改动 enable_support 的 op。"""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)

    def test_decide_without_model_keeps_project_setting(self):
        """decide() 不产出 enable_support 的 op，理由写明保留工程设置。"""
        profile = _profile_from_shape("shape_tower_overhang", self.td)
        decision = support_plan.decide(profile, mode="balanced", has_model=False)
        self.assertEqual(decision.ops, {})
        self.assertNotIn("enable_support", decision.ops)
        self.assertTrue(any("没有模型几何信息" in r for r in decision.reasons),
                        decision.reasons)

    def test_plan_without_model_returns_empty_ops(self):
        """plan() 没有模型画像时返回空 ops。"""
        profile = _profile_from_shape("shape_tower_overhang", self.td)
        ops, notes = support_plan.plan(profile, mode="balanced", has_model=False)
        self.assertEqual(ops, {})
        self.assertNotIn("enable_support", ops)
        self.assertTrue(any("没有模型几何信息" in n for n in notes), notes)


# ================================================================== 5）plan 合并

class TestPlanMerge(unittest.TestCase):
    """plan()：把形状原型的 ops 与几何算出的 ops 合并（几何值优先）。"""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)

    def test_plan_merges_proto_ops_with_geo_ops(self):
        """异型：原型给 max、几何给 set → 两条都在（几何的 set 不被吃掉）。"""
        profile = _heavy_profile()
        proto_ops = {"support_threshold_angle": {"max": 42},
                     "support_base_pattern_spacing": {"set": 3.0}}
        ops, _notes = support_plan.plan(profile, mode="balanced",
                                        proto_ops=proto_ops)
        angle_op = ops["support_threshold_angle"]
        self.assertIn("set", angle_op)
        self.assertIn("max", angle_op)
        self.assertEqual(angle_op["max"], 42)
        # 几何值优先：set 用几何算出来的角
        geo_angle = support_plan.decide(profile, mode="balanced") \
            .ops["support_threshold_angle"]["set"]
        self.assertEqual(angle_op["set"], geo_angle)

    def test_plan_drops_quantitative_support_keys(self):
        """支撑定量参数不再经 plan()，只保留「要不要 + 判定角」。"""
        profile = _heavy_profile()
        proto_ops = {"support_base_pattern_spacing": {"set": 3.0}}
        ops, _notes = support_plan.plan(profile, mode="balanced",
                                        proto_ops=proto_ops)
        self.assertNotIn("support_base_pattern_spacing", ops)
        self.assertTrue(set(ops).issubset(
            {"enable_support", "support_threshold_angle"}))

    def test_plan_keeps_non_support_proto_keys(self):
        """非支撑的原型键照常保留；支撑定量键由 support_model 统一决定，不再透传。"""
        profile = _heavy_profile()
        proto_ops = {"support_expansion": {"set": 0.3},
                     "outer_wall_speed": {"set": 60}}
        ops, _notes = support_plan.plan(profile, mode="balanced",
                                        proto_ops=proto_ops)
        self.assertNotIn("support_expansion", ops)
        self.assertEqual(ops.get("outer_wall_speed"), {"set": 60})

    def test_plan_without_proto_ops_matches_decide(self):
        """没有 proto_ops 时，plan() 的 ops 与 decide() 一致。"""
        profile = _heavy_profile()
        ops, _notes = support_plan.plan(profile, mode="quality")
        decision = support_plan.decide(profile, mode="quality")
        self.assertEqual(ops, decision.ops)

    def test_plan_accepts_new_keyword_arguments(self):
        """引擎侧会用这三个新关键字参数调用 plan()。"""
        profile = _heavy_profile()
        ops, notes = support_plan.plan(
            profile, mode="balanced", policy=None, proto_ops=None,
            user_threshold_angle=25.0, user_enable_support=True, has_model=True)
        self.assertTrue(ops)
        self.assertTrue(notes)
        self.assertEqual(ops["support_threshold_angle"]["set"], 25.0)

    def test_suggest_forwards_user_settings(self):
        """suggest() 把用户设置透传给支撑层。"""
        profile = _heavy_profile()
        ops, notes = shape_rules.suggest(
            profile, mode="balanced",
            user_threshold_angle=25.0, user_enable_support=True)
        self.assertEqual(ops["support_threshold_angle"]["set"], 25.0)
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
