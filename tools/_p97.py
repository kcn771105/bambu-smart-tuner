import io

p = "tests/test_adhesion_support.py"
s = io.open(p, encoding="utf-8").read()

tail = '''

class TestSupportModelSingleSource(unittest.TestCase):
    """支撑定量参数唯一来源：core/support_model.py。"""

    def _profile(self, overhang=600.0, size_z=40.0, foot=1600.0):
        obj = model_analysis.ObjectProfile(
            oid="1", index=0, size_x=40, size_y=40, size_z=size_z,
            min_z=0, max_z=size_z, volume=64_000, surface=9_600,
            overhang_area=overhang)
        return model_analysis.ModelProfile(
            objects=[obj], triangles=12, size_x=40, size_y=40, size_z=size_z,
            volume=obj.volume, surface=obj.surface,
            overhang_area=overhang, footprint=foot)

    def test_support_off_writes_nothing(self):
        su = support_model.tune(self._profile(), layer_height=0.2,
                                mode="balanced", values={"enable_support": 0})
        self.assertEqual(su.ops, {})

    def test_sparse_overhang_gets_loose_spacing(self):
        su = support_model.tune(self._profile(overhang=100), layer_height=0.2,
                                mode="balanced", values={"enable_support": 1})
        self.assertEqual(su.ops["support_base_pattern_spacing"], {"set": 3.0})

    def test_heavy_overhang_gets_dense_spacing_and_thick_interface(self):
        su = support_model.tune(self._profile(overhang=5000), layer_height=0.2,
                                mode="strength", values={"enable_support": 1})
        self.assertEqual(su.ops["support_base_pattern_spacing"], {"set": 1.6})
        self.assertEqual(su.ops["support_interface_top_layers"], {"set": 3})
        self.assertEqual(su.ops["support_interface_spacing"], {"set": 0.5})

    def test_gap_follows_layer_height(self):
        su = support_model.tune(self._profile(), layer_height=0.12,
                                mode="balanced", values={"enable_support": 1})
        self.assertEqual(su.ops["support_top_z_distance"], {"set": 0.12})
        self.assertGreaterEqual(su.ops["support_bottom_z_distance"]["set"], 0.15)

    def test_slender_gets_tree_strong(self):
        su = support_model.tune(self._profile(size_z=190, foot=900),
                                layer_height=0.2, mode="quality",
                                values={"enable_support": 1})
        self.assertEqual(su.ops["support_type"], {"set": "tree(auto)"})
        self.assertEqual(su.ops["support_style"], {"set": "tree_strong"})

    def test_speed_scales_with_mode_and_cap(self):
        base = dict(layer_height=0.2, values={"enable_support": 1})
        slow = support_model.tune(self._profile(), mode="ultrafine", max_speed=600, **base)
        fast = support_model.tune(self._profile(), mode="draft", max_speed=600, **base)
        self.assertLess(slow.ops["support_speed"]["set"], fast.ops["support_speed"]["set"])
        self.assertLessEqual(fast.ops["support_speed"]["set"], 600)
        # 接触面永远比本体慢
        self.assertLess(slow.ops["support_interface_speed"]["set"],
                        slow.ops["support_speed"]["set"])

    def test_quality_family_turns_on_ironing(self):
        su = support_model.tune(self._profile(), layer_height=0.16, mode="quality",
                                values={"enable_support": 1})
        self.assertEqual(su.ops["support_critical_regions_only"], {"set": True})
        self.assertIn("support_ironing_flow", su.ops)
        self.assertIn("support_ironing_spacing", su.ops)

    def test_balanced_does_not_touch_ironing(self):
        su = support_model.tune(self._profile(), layer_height=0.2, mode="balanced",
                                values={"enable_support": 1})
        self.assertNotIn("support_ironing_flow", su.ops)

    def test_rows_are_explainable(self):
        su = support_model.tune(self._profile(), layer_height=0.2, mode="balanced",
                                values={"enable_support": 1})
        self.assertTrue(su.rows)
        for r in su.rows:
            self.assertTrue(r.formula and r.conclusion)
'''

marker = 'if __name__ == "__main__":'
s = s.replace(marker, tail.strip("\n") + "\n\n\n" + marker, 1)

# 确保 import support_model
if "support_model" not in s.split(marker)[0]:
    s = s.replace("from core import model_analysis", "from core import model_analysis, support_model", 1)

io.open(p, "w", encoding="utf-8").write(s)
print("已补 TestSupportModelSingleSource 9 项")
