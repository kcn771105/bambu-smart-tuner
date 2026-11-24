"""逐件形状原型 → 参数策略（全工艺组覆盖）

核心思想
--------
Bambu Studio 的切片参数是**整盘全局**的，没法给每个对象单独设值。
但同一盘上的对象可以「脾气不同」：细杆怕晃、薄板怕翘、齿轮怕糊、花瓶怕断层。

所以做法是：

    1. 逐个对象算形状画像（core/model_analysis.py）
    2. 把每个对象判定成**形状原型**（tall_slim / flat_plate / thin_wall /
       vase / solid_block / small_detail / long_bar / overhanging /
       small_foot_tower / generic）
    3. 每个原型给出一套**覆盖全部工艺组**的参数建议（强度/质量/均衡 三档）
    4. 支撑策略单独由**模型几何**决定（core/support_plan.py）
    5. 合并成一个全局结果：**同一个键取所有对象里最保守的那个**

「最保守」的定义随参数语义变化（见 MERGE_DIR）：

    · 速度类   → 取最小（慢的赢，保证最脆弱的那个件不出问题）
    · 加速度类 → 取最小
    · 墙层/壳层 → 取最大（强度下限，最薄弱的件也够强）
    · 层高     → 取最小（细节优先）
    · 填充密度 → 取最大（强度优先）
    · 裙边     → 取最大（附着力下限）
    · 支撑间距 → 取大（好拆）、支撑底纹间距 → 取小（支撑更密）

规则表放在 rules/BambuRules.json 的 `shape_profiles` 节点，
支撑策略放在 `support_policy` 节点，用户可直接编辑，不用动主程序代码。
这里只内置一份兜底（规则文件缺该节点时用）。
"""

from __future__ import annotations

from dataclasses import dataclass

from . import modes as modes_registry
from . import model_analysis, support_plan


# ------------------------------------------------------------------ 原型定义

@dataclass(frozen=True)
class ShapeProto:
    key: str
    label: str
    desc: str


PROTOS: tuple[ShapeProto, ...] = (
    ShapeProto("tall_slim", "细高件", "高瘦、底面小，容易晃动"),
    ShapeProto("small_foot_tower", "小脚高塔", "底部接触面积极小的塔状件，最容易打飞"),
    ShapeProto("flat_plate", "扁平板", "大面积薄板，翘曲风险高"),
    ShapeProto("thin_wall", "薄壁/镂空", "壁薄或镂空，强度与外观都敏感"),
    ShapeProto("vase", "花瓶/容器", "开口容器，层间结合与外观都关键"),
    ShapeProto("long_bar", "细长条", "长径比大的杆件"),
    ShapeProto("overhanging", "大悬垂件", "悬垂面多，支撑与拉丝风险高"),
    ShapeProto("solid_block", "实心块", "实心厚件，强度由填充决定"),
    ShapeProto("small_detail", "小细节件", "小体积、多特征，怕糊"),
    ShapeProto("generic", "常规件", "没有明显偏向"),
)

PROTO_BY_KEY = {p.key: p for p in PROTOS}


# ------------------------------------------------------------------ 分类

def classify(obj: model_analysis.ObjectProfile) -> tuple[str, list[str]]:
    """判定单个对象的形状原型，返回 (原型键, 判定依据列表)。"""
    why: list[str] = []

    # 1) 小脚高塔：最危险，优先级最高
    if obj.footprint > 0 and obj.footprint < 900 and obj.size_z > 60:
        why.append(f"底面积仅 {obj.footprint:.0f} mm² 而高度 {obj.size_z:.0f} mm")
        return "small_foot_tower", why

    # 2) 扁平板
    if obj.flatness < 0.25 and obj.size_x > 20 and obj.size_y > 20:
        why.append(f"高 {obj.size_z:.0f} mm 仅为长边的 {obj.flatness:.2f} 倍")
        return "flat_plate", why

    # 3) 薄壁 / 镂空
    if obj.wall_thickness < 1.8 and obj.fill_ratio < 0.6:
        why.append(f"平均壁厚约 {obj.wall_thickness:.1f} mm、填充率 {obj.fill_ratio:.2f}")
        return "thin_wall", why

    # 4) 细长条（横向）
    if obj.plan_aspect < 0.45 and obj.size_z > 3:
        why.append(f"平面长宽比 {obj.plan_aspect:.2f}")
        return "long_bar", why

    # 5) 花瓶 / 开口容器
    if obj.top_cap_ratio < 0.15 and obj.fill_ratio < 0.5 and obj.size_z > 40:
        why.append(f"顶面封闭度仅 {obj.top_cap_ratio:.2f}（开口）")
        return "vase", why

    # 6) 细高件
    if obj.slender >= 2.6:
        why.append(f"细高比 {obj.slender:.2f}")
        return "tall_slim", why

    # 7) 大悬垂件
    if obj.overhang_ratio > 0.22:
        why.append(f"悬垂面占 {obj.overhang_ratio*100:.0f}%")
        return "overhanging", why

    # 8) 实心块
    if obj.fill_ratio > 0.6 and obj.volume > 20_000:
        why.append(f"填充率 {obj.fill_ratio:.2f}、体积 {obj.volume_cm3:.0f} cm³")
        return "solid_block", why

    # 9) 小细节件
    if obj.volume < 8000:
        why.append(f"体积仅 {obj.volume_cm3:.1f} cm³")
        return "small_detail", why

    why.append("未触发特殊特征")
    return "generic", why


# ------------------------------------------------------------------ 合并语义

# 每个键的合并方向：min=取最小（保守=慢/小），max=取最大（保守=多/强）
MERGE_DIR: dict[str, str] = {
    # ---- 速度：取最慢
    "outer_wall_speed": "min", "inner_wall_speed": "min",
    "sparse_infill_speed": "min", "internal_solid_infill_speed": "min",
    "top_surface_speed": "min", "support_speed": "min",
    "initial_layer_speed": "min", "initial_layer_infill_speed": "min",
    "gap_infill_speed": "min", "bridge_speed": "min",
    "overhang_1_4_speed": "min", "overhang_2_4_speed": "min",
    "overhang_3_4_speed": "min", "overhang_4_4_speed": "min",
    "travel_speed": "min", "wipe_speed": "min",
    # ---- 加速度：取最缓
    "outer_wall_acceleration": "min", "inner_wall_acceleration": "min",
    "sparse_infill_acceleration": "min", "internal_solid_infill_acceleration": "min",
    "top_surface_acceleration": "min", "initial_layer_acceleration": "min",
    "travel_acceleration": "min", "default_acceleration": "min",
    # ---- 强度下限：取最大
    "wall_loops": "max", "top_shell_layers": "max", "bottom_shell_layers": "max",
    "sparse_infill_density": "max", "infill_wall_overlap": "max",
    "top_bottom_infill_wall_overlap": "max", "top_surface_density": "max",
    "bottom_surface_density": "max", "top_shell_thickness": "max",
    "bottom_shell_thickness": "max", "minimum_sparse_infill_area": "max",
    # ---- 细节：取最小
    "layer_height": "min", "line_width": "min",
    "outer_wall_line_width": "min", "inner_wall_line_width": "min",
    "internal_solid_infill_line_width": "min", "sparse_infill_line_width": "min",
    "top_surface_line_width": "min", "support_line_width": "min",
    "initial_layer_line_width": "min", "initial_layer_print_height": "min",
    "resolution": "min", "min_feature_size": "min",
    # ---- 附着：取最大
    "brim_width": "max", "brim_type": "keep", "brim_object_gap": "min",
    "skirt_loops": "max", "skirt_distance": "max", "skirt_height": "max",
    "elefant_foot_compensation": "max", "raft_layers": "max",
    "raft_first_layer_density": "max", "raft_expansion": "max",
    # ---- 支撑：间隙取大（好拆）、底纹间距取小（支撑更密）
    "support_top_z_distance": "max", "support_bottom_z_distance": "max",
    "support_object_xy_distance": "max", "support_base_pattern_spacing": "min",
    "support_threshold_angle": "min", "support_interface_top_layers": "max",
    "support_interface_spacing": "min", "support_expansion": "max",
    "support_bottom_interface_spacing": "min",
    "support_object_first_layer_gap": "max",
    "tree_support_branch_angle": "max", "tree_support_branch_diameter": "min",
    "tree_support_branch_distance": "min", "tree_support_wall_count": "max",
    "support_ironing_flow": "min", "support_ironing_spacing": "min",
    # ---- 冷却：取最小（最怕拉丝的件赢）
    "fan_min_speed": "min", "fan_max_speed": "min", "overhang_fan_speed": "min",
    "fan_cooling_layer_time": "max", "close_fan_the_first_x_layers": "max",
    # ---- 回抽：取最小（最怕拉丝的件赢）
    "retraction_length": "min", "retraction_speed": "min",
    "deretraction_speed": "min", "z_hop": "max", "wipe_distance": "max",
    # ---- 接缝 / 熨烫
    "seam_gap": "min", "seam_slope_gap": "min", "seam_slope_steps": "max",
    "seam_slope_min_length": "min", "seam_slope_start_height": "max",
    "ironing_speed": "min", "ironing_spacing": "min", "ironing_inset": "max",
    "ironing_flow": "min", "ironing_width": "min",
    # ---- 其它
    "pressure_advance": "keep", "filament_flow_ratio": "keep",
    "top_surface_pattern": "keep", "sparse_infill_pattern": "keep",
    "internal_solid_infill_pattern": "keep", "infill_direction": "keep",
    "wall_generator": "keep", "reduce_crossing_wall": "keep",
    "bridge_flow": "keep", "smooth_coefficient": "keep",
    "enable_overhang_speed": "keep", "support_type": "keep",
    "support_style": "keep", "support_base_pattern": "keep",
    "support_interface_pattern": "keep", "seam_position": "keep",
    "seam_slope_type": "keep", "ironing_type": "keep",
    "ironing_pattern": "keep", "spiral_mode": "keep",
    "spiral_mode_smooth": "keep", "enable_support": "keep",
    "support_critical_regions_only": "keep",
    "support_remove_small_overhang": "keep", "print_sequence": "keep",
}


def _merge_op(a: dict, b: dict, direction: str = "keep", prefer: str = "a") -> dict:
    """合并两条 op（引擎侧语义：set 绝对赋值、mul/add 相对当前值、min/max 夹上下限）。

    两条 op 的运算类型**相同**时，按「更保守」的一侧合并：

        mul + mul → 累乘
        min + min → 取大（更紧的下限）
        max + max → 取小（更紧的上限）
        add + add → 取大
        set + set → 数值型取较小（direction="max" 的键取较大），非数值型保持先出现的那条；
                    prefer="b" 时以 b 为准（几何算出的值比形状原型更贴合本模型）

    两条 op 的运算类型**不同**时（例如形状原型给的 {"max": 42} 与几何算出的
    {"set": 38}），**两条约束都要保留**：结果里同时含两个键，绝不整条丢弃。
    引擎会先按 set 赋值，再按 min/max 夹上下限，语义正好成立
    （set=38 + max=42 → 最终 38°，几何算出的角度不会被原型吃掉）。

    无论同型还是异型，a、b 里原本存在的 op 键一个都不许丢。
    """
    return support_plan.merge_op(a, b, direction=direction, prefer=prefer)


# ------------------------------------------------------------------ 内置兜底规则
#
# 每个原型 × 三档模式，覆盖：速度 / 加速度 / 墙壳 / 填充 / 细节 / 附着 /
# 支撑 / 冷却 / 回抽 / 接缝 / 熨烫。
# 凡是"机器页/耗材页"的键（fan_*、retraction_*、z_hop 等）写在这里也不会被
# 写回——core/scope.py 的写入闸门会拦下来；它们在这里仅作参考基线。

BUILTIN_PROFILES: dict[str, dict[str, dict]] = {
    # ---------------------------------------------------------- 细高件
    "tall_slim": {
        "balanced": {
            # 速度/加速度：细高件最容易晃，压速降加速度
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.7},
            "travel_acceleration": {"mul": 0.75},
            "default_acceleration": {"mul": 0.85},
            "travel_speed": {"mul": 0.9},
            # 强度：底细要多圈壁才不晃
            "wall_loops": {"min": 4},
            "top_shell_layers": {"min": 4},
            "bottom_shell_layers": {"min": 4},
            "sparse_infill_density": {"min": 25},
            "infill_wall_overlap": {"min": 18},
            # 附着：细高件必须加大裙边
            "skirt_loops": {"min": 3},
            "elefant_foot_compensation": {"min": 0.1},
            # 支撑：高细件支架要多、密
        },
        "strength": {
            "outer_wall_speed": {"mul": 0.8},
            "outer_wall_acceleration": {"mul": 0.65},
            "default_acceleration": {"mul": 0.8},
            "travel_acceleration": {"mul": 0.7},
            "wall_loops": {"min": 5},
            "top_shell_layers": {"min": 5},
            "bottom_shell_layers": {"min": 5},
            "sparse_infill_density": {"min": 35},
            "infill_wall_overlap": {"min": 22},
            "skirt_loops": {"min": 4},
            "elefant_foot_compensation": {"min": 0.15},
        },
        "quality": {
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.7},
            "travel_speed": {"mul": 0.9},
            "wall_loops": {"min": 3},
            "top_shell_layers": {"min": 4},
            "layer_height": {"mul": 0.9},
            "seam_position": {"set": "aligned"},
        },
    },
    # ---------------------------------------------------------- 小脚高塔
    "small_foot_tower": {
        "balanced": {
            "outer_wall_speed": {"mul": 0.8},
            "travel_speed": {"mul": 0.85},
            "travel_acceleration": {"mul": 0.75},
            "outer_wall_acceleration": {"mul": 0.75},
            "initial_layer_speed": {"mul": 0.85},
            "initial_layer_acceleration": {"mul": 0.8},
            "wall_loops": {"min": 4},
            "skirt_loops": {"min": 4},
            "elefant_foot_compensation": {"min": 0.12},
        },
        "strength": {
            "outer_wall_speed": {"mul": 0.75},
            "outer_wall_acceleration": {"mul": 0.7},
            "initial_layer_speed": {"mul": 0.8},
            "wall_loops": {"min": 5},
            "sparse_infill_density": {"min": 30},
            "skirt_loops": {"min": 5},
            "elefant_foot_compensation": {"min": 0.15},
        },
        "quality": {
            "outer_wall_speed": {"mul": 0.8},
            "travel_speed": {"mul": 0.85},
            "initial_layer_speed": {"mul": 0.85},
            "wall_loops": {"min": 3},
            "layer_height": {"mul": 0.9},
        },
    },
    # ---------------------------------------------------------- 扁平板
    "flat_plate": {
        "balanced": {
            "initial_layer_speed": {"mul": 0.85},
            "initial_layer_acceleration": {"mul": 0.8},
            "initial_layer_line_width": {"mul": 1.05},
            "bottom_shell_layers": {"min": 4},
            "skirt_loops": {"min": 3},
            "elefant_foot_compensation": {"min": 0.12},
        },
        "strength": {
            "initial_layer_speed": {"mul": 0.8},
            "initial_layer_acceleration": {"mul": 0.75},
            "bottom_shell_layers": {"min": 5},
            "top_shell_layers": {"min": 5},
            "sparse_infill_density": {"min": 30},
            "elefant_foot_compensation": {"min": 0.15},
        },
        "quality": {
            "initial_layer_speed": {"mul": 0.85},
            "initial_layer_line_width": {"mul": 1.05},
            "bottom_shell_layers": {"min": 3},
            "elefant_foot_compensation": {"min": 0.1},
            "seam_position": {"set": "aligned"},
        },
    },
    # ---------------------------------------------------------- 薄壁/镂空
    "thin_wall": {
        "balanced": {
            "wall_loops": {"min": 3},
            "reduce_crossing_wall": {"set": True},
            "outer_wall_speed": {"mul": 0.9},
            "outer_wall_acceleration": {"mul": 0.85},
            "sparse_infill_density": {"max": 25},
            "top_surface_density": {"max": 25},
            "layer_height": {"mul": 0.95},
        },
        "strength": {
            "wall_loops": {"min": 4},
            "reduce_crossing_wall": {"set": True},
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.8},
            "sparse_infill_density": {"min": 30},
            "infill_wall_overlap": {"min": 18},
            "layer_height": {"mul": 0.95},
        },
        "quality": {
            "wall_loops": {"min": 3},
            "outer_wall_speed": {"mul": 0.9},
            "layer_height": {"mul": 0.9},
            "outer_wall_line_width": {"mul": 0.95},
            "seam_position": {"set": "aligned"},
        },
    },
    # ---------------------------------------------------------- 花瓶/容器
    "vase": {
        "balanced": {
            "wall_loops": {"min": 3},
            "outer_wall_speed": {"mul": 0.9},
            "outer_wall_acceleration": {"mul": 0.85},
            "spiral_mode_smooth": {"set": True},
            "top_surface_density": {"max": 30},
        },
        "strength": {
            "wall_loops": {"min": 4},
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.8},
            "spiral_mode_smooth": {"set": True},
            "top_surface_density": {"min": 35},
        },
        "quality": {
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.8},
            "layer_height": {"mul": 0.85},
            "spiral_mode_smooth": {"set": True},
            "seam_position": {"set": "aligned"},
        },
    },
    # ---------------------------------------------------------- 细长条
    "long_bar": {
        "balanced": {
            "outer_wall_acceleration": {"mul": 0.85},
            "travel_acceleration": {"mul": 0.85},
            "wall_loops": {"min": 3},
            "sparse_infill_density": {"min": 25},
        },
        "strength": {
            "wall_loops": {"min": 4},
            "outer_wall_acceleration": {"mul": 0.8},
            "travel_acceleration": {"mul": 0.8},
            "sparse_infill_density": {"min": 35},
            "infill_wall_overlap": {"min": 18},
        },
        "quality": {
            "outer_wall_speed": {"mul": 0.9},
            "layer_height": {"mul": 0.9},
            "wall_loops": {"min": 3},
        },
    },
    # ---------------------------------------------------------- 大悬垂件
    "overhanging": {
        "balanced": {
            "overhang_1_4_speed": {"mul": 0.8},
            "overhang_2_4_speed": {"mul": 0.85},
            "overhang_3_4_speed": {"mul": 0.9},
            "overhang_4_4_speed": {"mul": 0.9},
        },
        "strength": {
            "overhang_1_4_speed": {"mul": 0.75},
            "overhang_2_4_speed": {"mul": 0.8},
            "wall_loops": {"min": 3},
        },
        "quality": {
            "overhang_1_4_speed": {"mul": 0.75},
            "overhang_2_4_speed": {"mul": 0.8},
            "overhang_3_4_speed": {"mul": 0.8},
            "layer_height": {"mul": 0.95},
        },
    },
    # ---------------------------------------------------------- 实心块
    "solid_block": {
        "balanced": {
            "sparse_infill_density": {"min": 25},
            "sparse_infill_pattern": {"set": "gyroid"},
            "wall_loops": {"min": 3},
            "infill_wall_overlap": {"min": 16},
        },
        "strength": {
            "sparse_infill_density": {"min": 40},
            "sparse_infill_pattern": {"set": "gyroid"},
            "wall_loops": {"min": 4},
            "top_shell_layers": {"min": 5},
            "infill_wall_overlap": {"min": 20},
        },
        "quality": {
            "sparse_infill_density": {"max": 25},
            "sparse_infill_pattern": {"set": "grid"},
            "top_surface_pattern": {"set": "monotonicline"},
        },
    },
    # ---------------------------------------------------------- 小细节件
    "small_detail": {
        "balanced": {
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.85},
            "gap_infill_speed": {"mul": 0.85},
            "layer_height": {"mul": 0.85},
            "initial_layer_speed": {"mul": 0.85},
            "wall_loops": {"min": 3},
        },
        "strength": {
            "outer_wall_speed": {"mul": 0.85},
            "outer_wall_acceleration": {"mul": 0.85},
            "wall_loops": {"min": 3},
            "sparse_infill_density": {"min": 30},
        },
        "quality": {
            "outer_wall_speed": {"mul": 0.85},
            "gap_infill_speed": {"mul": 0.85},
            "layer_height": {"mul": 0.8},
            "initial_layer_line_width": {"mul": 1.05},
            "seam_position": {"set": "aligned"},
        },
    },
    # ---------------------------------------------------------- 常规件
    "generic": {"balanced": {}, "strength": {}, "quality": {}},
}


# ------------------------------------------------------------------ 对外接口

def default_suggestions(profile: model_analysis.ModelProfile, *,
                        layer_height: float = 0.2,
                        mode: str = "balanced") -> tuple[dict, list[str]]:
    """内置兜底实现（规则文件缺 shape_profiles 时用）。"""
    return suggest(profile, layer_height=layer_height, mode=mode,
                   profiles=BUILTIN_PROFILES)


def suggest(profile: model_analysis.ModelProfile, *,
            layer_height: float = 0.2,
            mode: str = "balanced",
            profiles: dict | None = None,
            support_policy: dict | None = None,
            user_threshold_angle: float | None = None,
            user_enable_support: bool | None = None,
            has_model: bool = True,
            mode_angle: float | None = None) -> tuple[dict, list[str]]:
    """逐对象判原型 → 逐对象出建议 → 合并成全局。

    返回 (合并后的 ops, 说明列表)。说明里会逐件列出原型与依据。
    support_policy：支撑策略阈值表（规则库 support_policy 节点），缺省用内置。
    user_threshold_angle / user_enable_support：工程里用户自己设的
        「悬垂判定角」与「启用支撑」开关，支撑层要尊重它们。
    has_model：有没有模型画像；为 False 时支撑层不做判断、不产出支撑 op。
    mode_angle：模式档自己算出来的判定角（度）；透传给支撑层，
        有它时支撑层以它为准，不再自行改一档。
    """
    profiles = profiles if profiles is not None else BUILTIN_PROFILES
    ops: dict[str, dict] = {}
    notes: list[str] = []
    per_obj: list[str] = []

    # 新模式（草稿/精细/超精细）在 shape_profiles 里没有专属节点时，
    # 继承同族的老档：草稿←均衡、精细/超精细←质量。
    base_mode = modes_registry.MODE_BASE_FALLBACK.get(mode, mode)
    drop_keys = modes_registry.DRAFT_DROP_KEYS if modes_registry.family(mode) == "draft" else frozenset()

    for obj in profile.objects:
        pkey, why = classify(obj)
        pnode = profiles.get(pkey) or {}
        node = pnode.get(mode) or pnode.get(base_mode) or pnode.get("balanced") or {}
        proto_label = PROTO_BY_KEY[pkey].label if pkey in PROTO_BY_KEY else pkey
        per_obj.append(f"件{obj.index + 1}（{obj.summary()}）→ {proto_label}"
                       + (f"（{'、'.join(why)}）" if why else ""))
        for key, op in node.items():
            if key in drop_keys:
                continue          # 草稿档不采纳「加厚」类建议
            direction = MERGE_DIR.get(key, "keep")
            if key in ops:
                ops[key] = _merge_op(ops[key], op, direction)
            else:
                ops[key] = dict(op)

    if per_obj:
        notes.append("逐件形状判定：" + "；".join(per_obj) + "。")
        if len(profile.objects) > 1:
            notes.append(
                f"盘面共 {len(profile.objects)} 个对象，已按「最保守者胜」合并"
                "（速度/加速度取最慢、墙层/壳层取最多、层高取最小、裙边取最宽）。")

    # ---- 支撑策略：由模型几何决定，并与形状层的支撑微调合并（约束一条不丢）
    try:
        sops, snotes = support_plan.plan(
            profile, mode=mode, policy=support_policy,
            proto_ops=ops,
            user_threshold_angle=user_threshold_angle,
            user_enable_support=user_enable_support,
            has_model=has_model,
            mode_angle=mode_angle)
        if sops:
            # plan() 返回的已经是「形状原型 ops + 几何支撑 ops」合并后的整体，
            # 直接整体接住，不再二次合并（否则 add/mul 会被叠加两次）。
            ops = sops
            notes.extend(snotes)
    except Exception as exc:              # 支撑层出错不影响主流程
        notes.append(f"支撑策略计算失败（已沿用默认支撑设置）：{exc}")

    return ops, notes


def proto_table() -> list[tuple[str, str, str]]:
    """给 UI 的原型说明表：(键, 中文名, 判定依据)。"""
    out = []
    for p in PROTOS:
        out.append((p.key, p.label, p.desc))
    return out


def per_object_detail(profile: model_analysis.ModelProfile, *,
                      mode: str = "balanced",
                      profiles: dict | None = None) -> list[dict]:
    """逐对象给出「判成什么形状原型 / 依据 / 该原型的建议参数」。

    给 UI 的「逐件调参明细」表格用。返回的每一项：

        index       对象序号（0 起）
        summary     尺寸 / 体积 / 壁厚 / 细高比 / 悬垂占比
        proto_key   形状原型键
        proto_label 形状原型中文名
        why         判定依据
        ops         该原型在这一档模式下的建议参数（键 → op 文本）
    """
    profiles = profiles if profiles is not None else BUILTIN_PROFILES
    out: list[dict] = []
    base_mode = modes_registry.MODE_BASE_FALLBACK.get(mode, mode)
    drop_keys = modes_registry.DRAFT_DROP_KEYS if modes_registry.family(mode) == "draft" else frozenset()
    for obj in profile.objects:
        pkey, why = classify(obj)
        pnode = profiles.get(pkey) or {}
        node = pnode.get(mode) or pnode.get(base_mode) or pnode.get("balanced") or {}
        ops_text = []
        for key, op in node.items():
            if key in drop_keys:
                continue
            if not isinstance(op, dict):
                continue
            kind = next(iter(op), "")
            val = op.get(kind)
            label = schema_label(key)
            if kind == "mul":
                ops_text.append(f"{label} ×{val:g}")
            elif kind == "set":
                ops_text.append(f"{label} → {val}")
            elif kind == "min":
                ops_text.append(f"{label} ≥ {val:g}")
            elif kind == "max":
                ops_text.append(f"{label} ≤ {val:g}")
            elif kind == "add":
                ops_text.append(f"{label} +{val:g}")
        out.append({
            "index": obj.index,
            "summary": obj.summary(),
            "proto_key": pkey,
            "proto_label": PROTO_BY_KEY[pkey].label if pkey in PROTO_BY_KEY else pkey,
            "why": "、".join(why) if why else "未触发特殊特征",
            "ops": "、".join(ops_text),
        })
    return out


def schema_label(key: str) -> str:
    """参数键 → 中文标签（查不到就用键名本身）。"""
    try:
        from . import schema
        s = schema.PARAMS.get(key)
        return s.label if s else key
    except Exception:
        return key
