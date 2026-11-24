import io

p = "tools/gen_studio_ui.py"
s = io.open(p, encoding="utf-8").read()

old = '''def load_mo()'''
new = '''# 页签按「键名前缀」推断（比 schema 分组准，schema 分组是我们自己的语义分组）
PREFIX_RULES = (
    ("多材料", ("brim_", "skirt_", "prime_tower_", "wipe_tower_", "flush_", "purge_")),
    ("支撑", ("support_", "tree_support_", "raft_", "enable_support")),
    ("速度", ("travel_", "initial_layer_travel_", "small_perimeter_", "gap_infill_speed",
              "bridge_speed", "overhang_", "first_layer_speed", "slowdown_",
              "enable_height_slowdown", "max_volumetric_speed")),
    ("质量", ("seam_", "ironing_", "elefant_foot", "xy_hole", "xy_contour", "arc_fitting",
              "resolution", "precise_", "layer_height", "line_width", "initial_layer_print_height",
              "slicing_mode", "has_scarf", "filter_out_gap_fill", "min_bead_width")),
    ("强度", ("wall_", "top_shell", "bottom_shell", "top_surface", "bottom_surface",
              "sparse_infill", "internal_solid_infill", "infill_", "top_fill", "bottom_fill",
              "only_one_wall", "alternate_extra_wall", "reduce_crossing_wall", "top_color",
              "bottom_color", "top_solid_infill", "skin_infill", "skeleton_infill",
              "minimum_sparse_infill", "top_bottom_infill", "solid_infill")),
)


def guess_tab(key: str, default: str) -> str:
    for tab, prefixes in PREFIX_RULES:
        if key.startswith(prefixes):
            return tab
    if key.endswith("_speed") or key.endswith("_acceleration"):
        return "速度"
    return default


GROUP_BY_KEY = {
    "wall_loops": "墙层数", "wall_sequence": "墙层数", "alternate_extra_wall": "墙层数",
    "reduce_crossing_wall": "墙层数", "only_one_wall_top": "墙层数",
    "top_shell_layers": "顶/底壳层数", "bottom_shell_layers": "顶/底壳层数",
    "top_shell_thickness": "顶/底壳层数", "bottom_shell_thickness": "顶/底壳层数",
    "top_surface_pattern": "顶/底壳层数", "bottom_surface_pattern": "顶/底壳层数",
    "top_surface_density": "顶/底壳层数", "bottom_surface_density": "顶/底壳层数",
    "sparse_infill_density": "填充", "sparse_infill_pattern": "填充",
    "infill_direction": "填充", "infill_wall_overlap": "填充",
    "internal_solid_infill_pattern": "填充", "internal_solid_infill_line_width": "填充",
    "outer_wall_speed": "其他层速度", "inner_wall_speed": "其他层速度",
    "sparse_infill_speed": "其他层速度", "internal_solid_infill_speed": "其他层速度",
    "top_surface_speed": "其他层速度", "initial_layer_speed": "其他层速度",
    "brim_width": "裙边", "brim_type": "裙边", "brim_object_gap": "裙边",
    "seam_position": "接缝", "seam_gap": "接缝", "staggered_inner_seams": "接缝",
    "ironing_type": "熨烫", "ironing_flow": "熨烫", "ironing_spacing": "熨烫",
    "ironing_speed": "熨烫", "ironing_inset": "熨烫", "ironing_direction": "熨烫",
    "support_base_pattern_spacing": "间距", "support_top_z_distance": "间距",
    "support_object_xy_distance": "间距", "support_interface_spacing": "间距",
    "support_base_pattern": "支撑样式", "support_threshold_angle": "角度",
    "enable_support": "启用", "support_interface_layers": "顶部界面层",
}


def load_mo()'''
assert old in s
s = s.replace(old, new, 1)

old2 = '''        rec = {"key": key, "label": spec.label, "tab": tab, "group": "",
               "studio_zh": "", "studio_en": "", "hidden": False, "note": ""}'''
new2 = '''        tab = guess_tab(key, tab)
        rec = {"key": key, "label": spec.label, "tab": tab,
               "group": GROUP_BY_KEY.get(key, ""),
               "studio_zh": "", "studio_en": "", "hidden": False, "note": ""}'''
assert old2 in s
s = s.replace(old2, new2, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("生成器加页签前缀推断 + 分组补全")
