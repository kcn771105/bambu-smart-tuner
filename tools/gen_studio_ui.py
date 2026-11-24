"""生成 data/studio_ui.json：每个工艺参数在 Bambu Studio 工艺面板里的位置与叫法。

三路合成：
1. 官方 zh_CN .mo 里的「英文 UI 名 → 中文 UI 名」，按键名归一后匹配（自动）；
2. 手工对照表 OVERRIDES（mo 里没有、或叫法差太远的）；
3. 剩下的标记 hidden=True：Studio 工艺面板没有这个开关，只能改文件。

跑法：
    python tools/gen_studio_ui.py
"""
import gettext
import io
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from core import schema, scope

MO = r"C:\Program Files\Bambu Studio\resources\i18n\zh_CN\BambuStudio.mo"
OUT = "data/studio_ui.json"

STOP = {"of", "the", "for", "and", "a", "an", "to", "in", "on", "with", "by",
        "maximum", "max", "minimum", "min", "enable", "use", "using", "when",
        "layer", "layers", "settings", "setting", "value", "only", "all"}


def words(s: str) -> frozenset:
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return frozenset(w for w in s.split() if w and w not in STOP)


# ---------------------------------------------------------------- 手工对照表
# key: (页签, 分组, Studio 里的中文名, Studio 里的英文名)
OVERRIDES: dict[str, tuple[str, str, str, str]] = {
    "layer_height": ("质量", "层高", "层高", "Layer height"),
    "initial_layer_print_height": ("质量", "层高", "首层层高", "Initial layer height"),
    "line_width": ("质量", "线宽", "默认", "Default"),
    "initial_layer_line_width": ("质量", "线宽", "首层", "Initial layer"),
    "initial_layer_infill_speed": ("速度", "其他层速度", "首层填充", "Initial layer infill"),
    "gap_infill_speed": ("速度", "其他层速度", "缝隙填充", "Gap fill"),
    "travel_speed": ("速度", "移动速度", "空驶", "Travel"),
    "bridge_speed": ("速度", "其他层速度", "桥接", "Bridge"),
    "overhang_1_4_speed": ("速度", "悬垂速度", "10%–25%", "Overhang wall 10%-25%"),
    "overhang_2_4_speed": ("速度", "悬垂速度", "25%–50%", "Overhang wall 25%-50%"),
    "overhang_3_4_speed": ("速度", "悬垂速度", "50%–75%", "Overhang wall 50%-75%"),
    "overhang_4_4_speed": ("速度", "悬垂速度", "75%–100%", "Overhang wall 75%-100%"),
    "enable_prime_tower": ("多材料", "擦料塔", "启用", "Enable"),
    "default_acceleration": ("速度", "加速度", "默认", "Normal printing"),
    "initial_layer_acceleration": ("速度", "加速度", "首层", "Initial layer"),
    "bridge_acceleration": ("速度", "加速度", "桥接", "Bridge"),
    "travel_acceleration": ("速度", "加速度", "空驶", "Travel"),
    "elefant_foot_compensation": ("质量", "精度", "象脚补偿", "Elephant foot compensation"),
    "elefant_foot_compensation_layers": ("质量", "精度", "象脚补偿层数", "Elephant foot compensation layers"),
    "xy_hole_compensation": ("质量", "精度", "孔洞补偿", "Hole compensation"),
    "xy_contour_compensation": ("质量", "精度", "轮廓补偿", "Contour compensation"),
    "enable_support": ("支撑", "启用", "启用支撑", "Enable support"),
    "support_type": ("支撑", "支撑样式", "类型", "Type"),
    "support_style": ("支撑", "支撑样式", "样式", "Style"),
    "support_angle": ("支撑", "角度", "支撑角度", "Support angle"),
    "support_interface_top_layers": ("支撑", "顶部界面层", "顶部界面层数", "Top interface layers"),
    "support_interface_bottom_layers": ("支撑", "底部界面层", "底部界面层数", "Bottom interface layers"),
    "support_interface_pattern": ("支撑", "顶部界面层", "界面图案", "Interface pattern"),
    "support_remove_small_overhang": ("支撑", "其他", "忽略小悬垂", "Ignore small overhang"),
    "enforce_support_layers": ("支撑", "其他", "强制支撑层", "Enforce support for the first"),
    "support_ironing_spacing": ("支撑", "支撑熨烫", "熨烫间距", "Ironing spacing"),
    "support_ironing_speed": ("支撑", "支撑熨烫", "熨烫速度", "Ironing speed"),
    "enable_support_ironing": ("支撑", "支撑熨烫", "启用支撑熨烫", "Enable support ironing"),
    "tree_support_branch_angle": ("支撑", "树状支撑", "分支角度", "Branch angle"),
    "tree_support_branch_diameter": ("支撑", "树状支撑", "分支直径", "Branch diameter"),
    "tree_support_branch_distance": ("支撑", "树状支撑", "分支间距", "Branch distance"),
    "tree_support_wall_count": ("支撑", "树状支撑", "树干壁数", "Support wall loops"),
    "raft_layers": ("支撑", "筏板", "筏板层数", "Raft layers"),
    "fuzzy_skin": ("其他", "毛绒表面", "毛绒皮肤", "Fuzzy skin"),
    "fuzzy_skin_first_layer": ("其他", "毛绒表面", "毛绒首层", "Fuzzy skin on first layer"),
    "fuzzy_skin_mode": ("其他", "毛绒表面", "毛绒模式", "Fuzzy skin mode"),
    "fuzzy_skin_noise_type": ("其他", "毛绒表面", "噪波类型", "Noise type"),
    "fuzzy_skin_octaves": ("其他", "毛绒表面", "噪波层数", "Noise octaves"),
    "fuzzy_skin_persistence": ("其他", "毛绒表面", "噪波持续性", "Noise persistence"),
    "fuzzy_skin_scale": ("其他", "毛绒表面", "噪波缩放", "Noise scale"),
    "spiral_mode": ("其他", "特殊模式", "螺旋花瓶模式", "Spiral vase"),
    "spiral_mode_max_xy_smoothing": ("其他", "特殊模式", "螺旋最大 XY 平滑", "Max XY smoothing"),
    "reduce_crossing_wall": ("强度", "墙层数", "减少交叉墙", "Reduce crossing wall"),
    "wall_sequence": ("强度", "墙层数", "墙顺序", "Wall sequence"),
    "precise_outer_wall": ("质量", "精度", "精确外壁", "Precise outer contour"),
    "alternate_extra_wall": ("强度", "墙层数", "交替额外墙", "Alternate extra wall"),
    "min_bead_width": ("质量", "精度", "最小挤出宽度", "Minimum wall width"),
    "skirt_per_object": ("多材料", "裙边", "每个对象单独裙边", "Skirt per object"),
    "bridge_angle": ("质量", "精度", "桥接方向", "Bridge direction"),
    "seam_slope_type": ("质量", "接缝", "斜接类型", "Scarf joint seam type"),
    "seam_slope_conditional": ("质量", "接缝", "条件斜接", "Conditional scarf"),
    "seam_slope_entire_loop": ("质量", "接缝", "整圈斜接", "Scarf entire loop"),
    "seam_slope_min_length": ("质量", "接缝", "斜接最小长度", "Scarf min length"),
    "seam_slope_start_height": ("质量", "接缝", "斜接起始高度", "Scarf start height"),
    "seam_slope_steps": ("质量", "接缝", "斜接步数", "Scarf steps"),
    "seam_slope_inner_walls": ("质量", "接缝", "内墙斜接", "Scarf inner walls"),
    "has_scarf_joint_seam": ("质量", "接缝", "启用斜接", "Scarf joint seam"),
    "small_perimeter_speed": ("速度", "其他层速度", "小周长速度", "Small perimeters"),
    "travel_speed_z": ("速度", "移动速度", "Z 空驶", "Z travel"),
    "max_travel_detour_distance": ("其他", "空走", "最大空走绕行", "Maximum detour"),
    "ooze_prevention": ("其他", "其他", "防流涎", "Ooze prevention"),
    "draft_shield": ("其他", "其他", "防风罩", "Draft shield"),
    "print_in_clockwise": ("其他", "其他", "顺时针打印", "Print sequence by clockwise"),
    "flush_into_objects": ("多材料", "冲刷", "冲刷到填充", "Flush into objects' infill"),
    "prime_tower_width": ("多材料", "擦料塔", "宽度", "Width"),
    "prime_tower_lift_height": ("多材料", "擦料塔", "抬升高度", "Lift height"),
    "prime_tower_lift_speed": ("多材料", "擦料塔", "抬升速度", "Lift speed"),
    "prime_tower_max_speed": ("多材料", "擦料塔", "最大速度", "Max speed"),
    "prime_tower_rib_wall": ("多材料", "擦料塔", "肋墙", "Rib wall"),
    "prime_tower_infill_gap": ("多材料", "擦料塔", "填充间隙", "Infill gap"),
    "prime_tower_enable_framework": ("多材料", "擦料塔", "骨架", "Framework"),
    "prime_tower_flat_ironing": ("多材料", "擦料塔", "平面熨烫", "Flat ironing"),
    "wipe_tower_no_sparse_layers": ("多材料", "擦料塔", "不生成稀疏层", "No sparse layers"),
    "sparse_infill_lattice_angle_1": ("强度", "填充", "网格角度 1", "Lattice angle 1"),
    "sparse_infill_lattice_angle_2": ("强度", "填充", "网格角度 2", "Lattice angle 2"),
    "filter_out_gap_fill": ("质量", "精度", "过滤缝隙填充", "Filter out gap fill"),
    "is_infill_first": ("强度", "填充", "先打填充", "Infill first"),
    "top_color_penetration_layers": ("强度", "顶/底壳层数", "顶部颜色渗透层数", "Top color penetration layers"),
    "bottom_color_penetration_layers": ("强度", "顶/底壳层数", "底部颜色渗透层数", "Bottom color penetration layers"),
    "top_solid_infill_flow_ratio": ("强度", "填充", "顶面实心流量比", "Top solid infill flow"),
    "slowdown_start_height": ("速度", "按高度降速", "起始高度", "Slowdown start height"),
    "slowdown_end_height": ("速度", "按高度降速", "结束高度", "Slowdown end height"),
    "slowdown_start_acc": ("速度", "按高度降速", "起始加速度", "Slowdown start acceleration"),
    "slowdown_end_acc": ("速度", "按高度降速", "结束加速度", "Slowdown end acceleration"),
    "enable_height_slowdown": ("速度", "按高度降速", "启用按高度降速", "Enable height slowdown"),
}

# Studio 工艺面板没有的（隐藏参数），标明原因
HIDDEN: dict[str, str] = {
    "support_density": "Studio 用「支撑线距」代替密度，没有密度滑块",
    "conformal_infill": "实验性共形填充，界面上没有",
    "conformal_pole": "实验性共形填充，界面上没有",
    "conformal_ray_count": "实验性共形填充，界面上没有",
    "conformal_hub_radius": "实验性共形填充，界面上没有",
    "conformal_stagger": "实验性共形填充，界面上没有",
    "conformal_link_flip_layers": "实验性共形填充，界面上没有",
    "conformal_link_keep_layers": "实验性共形填充，界面上没有",
    "interlocking_beam": "互锁梁（新版实验特性），界面上没有",
    "interlocking_beam_layer_count": "互锁梁（新版实验特性），界面上没有",
    "interlocking_orientation": "互锁梁（新版实验特性），界面上没有",
    "accel_to_decel_enable": "加减速比是 Orca 的开关，Bambu 界面没有",
    "accel_to_decel_factor": "加减速比是 Orca 的参数，Bambu 界面没有",
    "counterbore_hole_bridging": "沉孔桥接，界面上没有",
    "infill_instead_top_bottom_surfaces": "用填充代替顶底面，界面上没有",
    "enable_order_independent_overlap_carving": "重叠裁切实验项，界面上没有",
    "embedding_wall_into_infill": "墙嵌入填充，界面上没有",
    "z_direction_outwall_speed_continuous": "Z 方向连续外壁速度，界面上没有",
    "modifier_ignore_infill": "修改器忽略填充，界面上没有",
    "support_interface_not_for_body": "支撑界面只用于支撑，界面上没有",
    "support_cooling_filter": "支撑冷却过滤，界面上没有",
    "support_fast_purge_mode": "支撑快速冲刷，界面上没有",
    "enable_tower_interface_features": "擦料塔界面特性，界面上没有",
    "circle_compensation_manual_offset": "圆孔补偿手动偏移，界面上没有",
    "enable_circle_compensation": "圆孔补偿，界面上没有",
    "travel_short_distance_acceleration": "短距空走加速度，界面上没有",
    "initial_layer_travel_acceleration": "首层空驶加速度，界面上没有",
    "prime_tower_skip_points": "擦料塔跳过点，界面上没有",
    "first_x_layer_fan_speed": "属耗材页（风扇），工艺面板没有",
    "monotonic_travel_into_wall": "单调空走进墙，界面上没有",
    "wall_transition_angle": "Arachne 墙过渡角度，界面上没有",
    "wall_transition_filter_deviation": "Arachne 墙过渡过滤偏差，界面上没有",
    "bridge_no_support": "桥接不生成支撑，界面上没有",
    "sparse_infill_anchor": "锚点参数，界面上没有",
    "sparse_infill_anchor_max": "锚点参数，界面上没有",
    "mmu_segmented_region_max_width": "多色分区，界面上没有",
    "mmu_segmented_region_interlocking_depth": "多色分区，界面上没有",
    "mmu_segmented_region_use_max_width": "多色分区，界面上没有",
    "start_end_points": "擦嘴/起终点坐标，界面上没有",
}

# ---------------------------------------------------------------- 页签启发式
GROUP_TAB = {
    "quality": "质量",
    "wall": "强度",
    "infill": "强度",
    "seam": "质量",
    "ironing": "质量",
    "speed": "速度",
    "accel": "速度",
    "support": "支撑",
    "tower": "多材料",
    "adhesion": "多材料",
    "z": "其他",
    "cooling": "其他",
}


# 页签按「键名前缀」推断（比 schema 分组准，schema 分组是我们自己的语义分组）
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


def load_mo() -> dict[frozenset, list[tuple[str, str]]]:
    with io.open(MO, "rb") as f:
        cat = gettext.GNUTranslations(f)._catalog
    index: dict[frozenset, list[tuple[str, str]]] = defaultdict(list)
    for en, zh in cat.items():
        if not (isinstance(en, str) and isinstance(zh, str) and en and zh and en != zh):
            continue
        w = words(en)
        if w and len(zh) <= 40:
            index[w].append((en, zh))
    return index


def mo_match(key: str, index):
    kw = words(key)
    if not kw:
        return None
    if kw in index and len(index[kw]) == 1:
        return index[kw][0]
    cands = []
    for cw, items in index.items():
        if not cw:
            continue
        inter = kw & cw
        if not inter:
            continue
        union = kw | cw
        if len(inter) / len(union) < 0.6:
            continue
        cands.append((len(union), items))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    if len(cands) > 1 and cands[1][0] == cands[0][0]:
        return None
    if len(cands[0][1]) != 1:
        return None
    return cands[0][1][0]


def main() -> int:
    index = load_mo()
    out: dict[str, dict] = {}
    stat = {"override": 0, "mo": 0, "hidden": 0, "unknown": 0}
    for key, spec in schema.PARAMS.items():
        if scope.SCOPE.get(key) != "process":
            continue
        tab = GROUP_TAB.get(spec.group, "其他")
        tab = guess_tab(key, tab)
        rec = {"key": key, "label": spec.label, "tab": tab,
               "group": GROUP_BY_KEY.get(key, ""),
               "studio_zh": "", "studio_en": "", "hidden": False, "note": ""}
        if key in OVERRIDES:
            tab2, grp, zh, en = OVERRIDES[key]
            rec.update(tab=tab2, group=grp, studio_zh=zh, studio_en=en)
            stat["override"] += 1
        elif key in HIDDEN:
            rec.update(hidden=True, note=HIDDEN[key])
            stat["hidden"] += 1
        else:
            hit = mo_match(key, index)
            if hit:
                rec.update(studio_en=hit[0], studio_zh=hit[1])
                stat["mo"] += 1
            else:
                stat["unknown"] += 1
        out[key] = rec

    # 未知项统一标注：界面上没搜到同名条目，给英文键名当搜索词
    for rec in out.values():
        if not rec["studio_zh"] and not rec["hidden"]:
            rec["note"] = "Studio 界面上没搜到同名条目，可试搜索：" + rec["key"].replace("_", " ")

    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps({"meta": {"source": "Bambu Studio zh_CN + 手工对照",
                             "count": len(out), "stat": stat},
                    "items": out}, ensure_ascii=False, indent=1))
    print("已写", OUT, len(out), "条 →", stat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
