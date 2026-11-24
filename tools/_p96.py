import io

# ---------- 1) test_layers.py：decide 不再产定量 op，断言改到 support_model
p = "tests/test_layers.py"
s = io.open(p, encoding="utf-8").read()
old = '''    def test_decide_very_high_overhang_uses_critical_regions(self):
        """悬垂占比超过 critical 阈值：只生成关键区域支撑，支撑更密。"""'''
new = '''    def test_decide_very_high_overhang_uses_critical_regions(self):
        """悬垂很重：decide 只给「要不要 + 判定角」，定量交给 support_model。"""'''
assert old in s
s = s.replace(old, new, 1)

old_body = '''        decision = support_plan.decide(profile, mode="balanced")
        self.assertTrue(decision.enable)
        self.assertEqual(decision.ops.get("support_critical_regions_only"),
                         {"set": True})
        # 悬垂很重 → 触发角放宽、间距更密
        self.assertLessEqual(decision.ops["support_threshold_angle"]["set"],
                             support_plan.BUILTIN_POLICY["angle_overhang_critical_deg"])
        self.assertLessEqual(decision.ops["support_base_pattern_spacing"]["set"],
                             support_plan.BUILTIN_POLICY["spacing_dense"])'''
new_body = '''        decision = support_plan.decide(profile, mode="balanced")
        self.assertTrue(decision.enable)
        # 决策层只交出两个键，定量参数不再由它写（否则会和 support_model 抢写）
        self.assertTrue(set(decision.ops).issubset(
            {"enable_support", "support_threshold_angle"}))
        self.assertLessEqual(decision.ops["support_threshold_angle"]["set"],
                             support_plan.BUILTIN_POLICY["angle_overhang_critical_deg"])

        # 定量交给 support_model：大面积悬垂 → 接触面 3 层、线距 0.5
        from core import support_model
        su = support_model.tune(profile, layer_height=0.2, mode="balanced",
                                values={"enable_support": 1})
        self.assertEqual(su.ops["support_interface_top_layers"], {"set": 3})
        self.assertEqual(su.ops["support_interface_spacing"], {"set": 0.5})
        self.assertLessEqual(su.ops["support_base_pattern_spacing"]["set"], 2.0)'''
assert old_body in s
s = s.replace(old_body, new_body, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("test_layers 已改")

# ---------- 2) test_shape_support.py：plan 不再合并支撑定量键
p2 = "tests/test_shape_support.py"
s2 = io.open(p2, encoding="utf-8").read()
old2 = '''    def test_plan_same_type_set_prefers_geometry_value(self):
        """同型 set + set → 取几何算出的值。"""
        profile = _heavy_profile()
        proto_ops = {"support_base_pattern_spacing": {"set": 3.0}}
        ops, _notes = support_plan.plan(profile, mode="balanced",
                                        proto_ops=proto_ops)
        geo_spacing = support_plan.decide(profile, mode="balanced") \\
            .ops["support_base_pattern_spacing"]["set"]
        self.assertEqual(ops["support_base_pattern_spacing"]["set"], geo_spacing)'''
new2 = '''    def test_plan_drops_quantitative_support_keys(self):
        """支撑定量参数不再经 plan()，只保留「要不要 + 判定角」。"""
        profile = _heavy_profile()
        proto_ops = {"support_base_pattern_spacing": {"set": 3.0}}
        ops, _notes = support_plan.plan(profile, mode="balanced",
                                        proto_ops=proto_ops)
        self.assertNotIn("support_base_pattern_spacing", ops)
        self.assertTrue(set(ops).issubset(
            {"enable_support", "support_threshold_angle"}))'''
assert old2 in s2
s2 = s2.replace(old2, new2, 1)
io.open(p2, "w", encoding="utf-8").write(s2)
print("test_shape_support 已改")
