"""几何驱动的通用调参层：把「模型长什么样」翻译成工艺参数调整。

为什么需要这一层
----------------
``core/shape_rules.py`` 按「形状原型」出建议（细高件、扁平板、花瓶……），
原型有 10 种，覆盖面天然有限——实测只有 34 个工艺参数被它触及，
而切片工艺页一共有 272 项。

这一层换了个思路：**不按原型枚举，而是按几何事实枚举**。

    模型细高（细高比 > 3）        → 降速降加速度、加壁层、加裙边
    模型是大平板（扁平度 < 0.2）   → 降首层速度、加大附着、禁熨烫
    模型壁薄（壁厚 < 1.8 mm）      → 关交叉墙、提层高上限、防糊
    模型悬垂面多                 → 降悬垂速度、收紧支撑阈值
    模型是开口容器               → 启用螺旋模式平滑
    ……

几何事实一共十几种（细高比 / 扁平度 / 壁厚 / 填充率 / 悬垂占比 / 高度 /
体积 / 开口度 / 是否贴板 / 多件……），每种事实对应一批参数动作。
组合起来就能覆盖到绝大多数工艺参数，而且**新增参数只要在 RULES 里加一行**。

规则表放在规则库的 ``geometry_rules`` 节点，用户可直接编辑
（用 ``tools/_sync_geometry_rules.py --apply`` 可把内置表导回规则库）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import modes as modes_registry
from . import model_analysis


# ------------------------------------------------------------------ 几何上下文

@dataclass
class GeomCtx:
    """一次优化里用到的全部几何事实。"""

    # 场景级
    height: float = 0.0
    volume_cm3: float = 0.0
    overhang_ratio: float = 0.0          # 悬垂面占比（体积加权）
    on_plate: bool = True                # 有对象贴着平台
    object_count: int = 0
    max_volume_cm3: float = 0.0

    # 最"挑事"的那个对象的指标（保守起见按最坏取值）
    slender: float = 0.0                 # 细高比
    flatness: float = 1.0                # 高 / 长边
    plan_aspect: float = 1.0             # 平面长宽比
    wall_thickness: float = 0.0          # 平均壁厚
    fill_ratio: float = 0.0              # 体积 / 包围盒体积
    top_cap_ratio: float = 1.0           # 顶面封闭度（开口容器 < 0.15）
    neck_ratio: float = 1.0              # 中段宽度 / 最大宽度
    footprint_mm2: float = 0.0
    mid_width_mm: float = 0.0
    overhang_max: float = 0.0            # 单件最大悬垂占比

    # 派生
    @property
    def is_solid(self) -> bool:
        return self.fill_ratio > 0.55

    @property
    def is_thin(self) -> bool:
        return self.wall_thickness > 0 and self.wall_thickness < 1.8

    @property
    def is_open(self) -> bool:
        return self.top_cap_ratio < 0.15

    @property
    def is_multi(self) -> bool:
        return self.object_count > 1


def build_ctx(profile: model_analysis.ModelProfile) -> GeomCtx:
    """从模型画像里提炼几何事实。"""
    ctx = GeomCtx()
    objs = list(profile.objects)
    if not objs:
        return ctx
    ctx.object_count = len(objs)
    ctx.height = max(o.max_z for o in objs) - min(o.min_z for o in objs)
    ctx.on_plate = min(o.min_z for o in objs) < 0.6

    weights = [max(o.volume, 1.0) for o in objs]
    wsum = sum(weights)
    ctx.overhang_ratio = sum(o.overhang_ratio * w for o, w in zip(objs, weights)) / wsum
    ctx.volume_cm3 = sum(o.volume_cm3 for o in objs)
    ctx.max_volume_cm3 = max(o.volume_cm3 for o in objs)

    def worst(attr: str, mode: str = "max") -> float:
        vals = [getattr(o, attr) for o in objs]
        return (max(vals) if mode == "max" else min(vals))

    ctx.slender = worst("slender")
    ctx.flatness = worst("flatness", "min")
    ctx.plan_aspect = worst("plan_aspect", "min")
    ctx.wall_thickness = worst("wall_thickness", "min")
    ctx.fill_ratio = worst("fill_ratio", "min")
    ctx.top_cap_ratio = worst("top_cap_ratio", "min")
    ctx.neck_ratio = worst("neck_ratio", "min")
    ctx.overhang_max = worst("overhang_ratio")
    ctx.footprint_mm2 = sum(o.footprint for o in objs)
    ctx.mid_width_mm = min(o.mid_width for o in objs)
    return ctx


# ------------------------------------------------------------------ 条件

#: 条件名 → 判定函数。写规则时只引用条件名。
CONDS: dict[str, Callable[[GeomCtx], bool]] = {
    "always":            lambda c: True,
    "never":             lambda c: False,
    "slender_gt_2_5":    lambda c: c.slender >= 2.5,
    "slender_gt_4":      lambda c: c.slender >= 4.0,
    "flat_lt_0_25":      lambda c: c.flatness < 0.25,
    "flat_lt_0_15":      lambda c: c.flatness < 0.15,
    "thin_lt_1_8":       lambda c: c.wall_thickness > 0 and c.wall_thickness < 1.8,
    "thin_lt_1_2":       lambda c: c.wall_thickness > 0 and c.wall_thickness < 1.2,
    "solid_gt_0_55":     lambda c: c.fill_ratio > 0.55,
    "open_top":          lambda c: c.top_cap_ratio < 0.15,
    "narrow_neck":       lambda c: c.neck_ratio < 0.6,
    "long_bar":          lambda c: c.plan_aspect < 0.45,
    "overhang_gt_0_12":  lambda c: c.overhang_ratio >= 0.12,
    "overhang_gt_0_22":  lambda c: c.overhang_ratio >= 0.22,
    "overhang_lt_0_05":  lambda c: c.overhang_ratio < 0.05,
    "tall_gt_90":        lambda c: c.height >= 90.0,
    "tall_gt_160":       lambda c: c.height >= 160.0,
    "small_lt_10cc":     lambda c: c.max_volume_cm3 < 10.0,
    "big_gt_60cc":       lambda c: c.max_volume_cm3 > 60.0,
    "multi_object":      lambda c: c.object_count > 1,
    "not_on_plate":      lambda c: not c.on_plate,
    "small_footprint":   lambda c: 0 < c.footprint_mm2 < 1500,
    # 盘面里存在小体积件：总件数 > 1 且最大件的体积也不大
    "small_detail":      lambda c: c.object_count > 1 and c.max_volume_cm3 < 20.0,
}


@dataclass
class Rule:
    """一条几何驱动的参数动作。"""
    key: str
    cond: str
    op: dict
    reason: str
    modes: tuple[str, ...] = ()          # 空 = 三种模式都生效
    priority: int = 0                    # 数字小的先应用，后面的可覆盖


def _r(key: str, cond: str, op: dict, reason: str,
       modes: tuple[str, ...] = (), priority: int = 0) -> Rule:
    return Rule(key=key, cond=cond, op=op, reason=reason, modes=modes, priority=priority)


# ------------------------------------------------------------------ 规则表
#
# 覆盖：质量与线宽 / 填充 / 速度 / 加速度 / Z 与补偿 / 悬垂与支撑 / 首层粘合 /
#       熨烫 / 接缝与斜切 / 墙体高级 / 擦料塔。
# 凡是纯「功能开关 + 噪声参数」（磨砂噪声、螺旋平滑上限）不在表内——
# 它们与几何无关，由用户自己决定。

RULES: list[Rule] = [
    # ============================================================ 质量与线宽
    _r("layer_height", "always", {"mul": 1.0}, "基准层高（几何层不乱改层高）", priority=99),
    _r("layer_height", "small_detail", {"mul": 0.85},
       "有小体积件，层高压小保细节", modes=("quality",)),
    _r("layer_height", "big_gt_60cc", {"mul": 1.0}, "大件保持基准层高"),
    _r("resolution", "always", {"set": 0.012}, "曲面精度基准值 0.012 mm"),
    _r("min_feature_size", "thin_lt_1_8", {"mul": 0.9},
       "薄壁件特征很小，最小特征尺寸同步收紧", priority=10),
    _r("line_width", "always", {"mul": 1.0}, "基准线宽（由喷嘴缩放层处理）", priority=99),
    _r("outer_wall_line_width", "always", {"mul": 1.0}, "外壁线宽跟随基准", priority=99),
    _r("inner_wall_line_width", "always", {"mul": 1.0}, "内壁线宽跟随基准", priority=99),
    _r("internal_solid_infill_line_width", "always", {"mul": 1.0}, "内部实心线宽跟随基准", priority=99),
    _r("sparse_infill_line_width", "always", {"mul": 1.0}, "稀疏填充线宽跟随基准", priority=99),
    _r("top_surface_line_width", "always", {"mul": 1.0}, "顶面线宽跟随基准", priority=99),
    _r("support_line_width", "always", {"mul": 1.0}, "支撑线宽跟随基准", priority=99),
    _r("initial_layer_line_width", "flat_lt_0_25", {"mul": 1.05},
       "大平板首层加宽，压住翘曲"),
    _r("initial_layer_line_width", "small_lt_10cc", {"mul": 1.05},
       "小件首层加宽，贴板更稳"),
    _r("initial_layer_print_height", "flat_lt_0_15", {"mul": 0.85},
       "超薄板首层压薄，避免翘边"),
    _r("initial_layer_print_height", "always", {"mul": 1.0}, "首层高度跟随基准", priority=99),
    _r("spiral_mode", "open_top", {"set": True},
       "开口容器启用螺旋模式，层间无缝"),
    _r("spiral_mode_smooth", "open_top", {"set": True},
       "开口容器启用螺旋 XY 平滑"),
    _r("spiral_mode_max_xy_smoothing", "open_top", {"set": 60},
       "螺旋平滑上限收到 60%，避免 XY 抖动", priority=10),

    # ============================================================ 填充
    _r("sparse_infill_density", "solid_gt_0_55", {"min": 30},
       "实心厚件靠填充给强度，密度上调"),
    _r("sparse_infill_density", "thin_lt_1_8", {"max": 25},
       "薄壁镂空件填充过密反而挤变形，密度上限压住"),
    _r("sparse_infill_density", "always", {"mul": 1.0}, "填充密度跟随模式档", priority=99),
    _r("sparse_infill_pattern", "solid_gt_0_55", {"set": "gyroid"},
       "实心件用 gyroid，抗剪强度更高"),
    _r("internal_solid_infill_pattern", "solid_gt_0_55", {"set": "concentric"},
       "内部实心填充用 concentric，环形闭合抗剪"),
    _r("internal_solid_infill_pattern", "thin_lt_1_8", {"set": "zig-zag"},
       "薄壁件用 zig-zag，路径规整不挤壁"),
    _r("top_surface_pattern", "open_top", {"set": "monotonicline"},
       "开口件顶面用单调线，表面更整"),
    _r("infill_wall_overlap", "always", {"mul": 1.0}, "重叠率跟随模式档", priority=99),
    _r("top_bottom_infill_wall_overlap", "solid_gt_0_55", {"min": 15},
       "实心件顶底与墙重叠加大，防分层"),
    _r("infill_direction", "always", {"set": 45}, "填充走线角度基准 45°"),
    _r("minimum_sparse_infill_area", "thin_lt_1_8", {"mul": 0.6},
       "薄壁件忽略小填充区域，减少碎线"),

    # ============================================================ 速度
    _r("outer_wall_speed", "slender_gt_2_5", {"mul": 0.9},
       "细高件降外壁速度，防晃动"),
    _r("outer_wall_speed", "thin_lt_1_8", {"mul": 0.92},
       "薄壁件略降外壁速度，防拉丝"),
    _r("outer_wall_speed", "always", {"mul": 1.0}, "外壁速度跟随模式档", priority=99),
    _r("inner_wall_speed", "slender_gt_2_5", {"mul": 0.92},
       "细高件内壁同步降速"),
    _r("inner_wall_speed", "always", {"mul": 1.0}, "内壁速度跟随模式档", priority=99),
    _r("sparse_infill_speed", "solid_gt_0_55", {"mul": 0.95},
       "实心件填充降速，减少流量尖峰"),
    _r("sparse_infill_speed", "always", {"mul": 1.0}, "稀疏填充速度跟随模式档", priority=99),
    _r("internal_solid_infill_speed", "solid_gt_0_55", {"mul": 0.95},
       "内部实心降速"),
    _r("internal_solid_infill_speed", "always", {"mul": 1.0}, "内部实心速度跟随模式档", priority=99),
    _r("top_surface_speed", "open_top", {"mul": 0.9},
       "开口件顶面降速，表面更光"),
    _r("top_surface_speed", "always", {"mul": 1.0}, "顶面速度跟随模式档", priority=99),
    _r("initial_layer_speed", "flat_lt_0_25", {"mul": 0.85},
       "大平板首层降速，贴牢不翘"),
    _r("initial_layer_speed", "small_lt_10cc", {"mul": 0.9},
       "小件首层降速，粘牢"),
    _r("initial_layer_speed", "always", {"mul": 1.0}, "首层速度跟随模式档", priority=99),
    _r("initial_layer_infill_speed", "flat_lt_0_25", {"mul": 0.9},
       "大平板首层填充同步降速"),
    _r("initial_layer_infill_speed", "always", {"mul": 1.0}, "首层填充速度跟随模式档", priority=99),
    _r("travel_speed", "slender_gt_2_5", {"mul": 0.92},
       "细高件空走降速，减小晃动"),
    _r("travel_speed", "always", {"mul": 1.0}, "空走速度跟随模式档", priority=99),
    _r("support_speed", "overhang_gt_0_22", {"mul": 1.0},
       "支撑速度由「支撑按模型尺寸」层按机型上限与模式决定", priority=99),
    _r("support_speed", "always", {"mul": 1.0}, "支撑速度跟随模式档", priority=99),
    _r("bridge_speed", "overhang_gt_0_22", {"mul": 0.85},
       "桥接多的件降桥接速度，防断"),
    _r("bridge_speed", "always", {"mul": 1.0}, "桥接速度跟随模式档", priority=99),
    _r("gap_infill_speed", "thin_lt_1_8", {"mul": 0.9},
       "薄壁件缝隙填充降速，防糊"),
    _r("gap_infill_speed", "always", {"mul": 1.0}, "缝隙填充速度跟随模式档", priority=99),
    _r("wipe_speed", "always", {"mul": 1.0}, "擦嘴速度跟随模式档", priority=99),
    _r("overhang_1_4_speed", "overhang_gt_0_22", {"mul": 0.85},
       "悬垂面多，1/4 悬垂降速"),
    _r("overhang_2_4_speed", "overhang_gt_0_22", {"mul": 0.88},
       "悬垂面多，1/2 悬垂降速"),
    _r("overhang_3_4_speed", "overhang_gt_0_22", {"mul": 0.9},
       "悬垂面多，3/4 悬垂降速"),
    _r("overhang_4_4_speed", "overhang_gt_0_22", {"mul": 0.92},
       "悬垂面多，接近垂直面降速"),
    _r("enable_overhang_speed", "overhang_gt_0_12", {"set": True},
       "悬垂面多，启用分组悬垂降速"),
    _r("bridge_angle", "overhang_gt_0_22", {"set": 45},
       "桥接方向统一 45°，最省支撑"),

    # ============================================================ 加速度
    _r("outer_wall_acceleration", "slender_gt_2_5", {"mul": 0.85},
       "细高件降外壁加速度，防甩"),
    _r("outer_wall_acceleration", "thin_lt_1_8", {"mul": 0.9},
       "薄壁件降外壁加速度"),
    _r("outer_wall_acceleration", "always", {"mul": 1.0}, "外壁加速度跟随模式档", priority=99),
    _r("internal_solid_infill_acceleration", "solid_gt_0_55", {"mul": 0.9},
       "内部实心降加速度"),
    _r("top_surface_acceleration", "open_top", {"mul": 0.9},
       "开口件顶面降加速度，层纹更轻"),
    _r("top_surface_acceleration", "always", {"mul": 1.0}, "顶面加速度跟随模式档", priority=99),
    _r("initial_layer_acceleration", "flat_lt_0_25", {"mul": 0.85},
       "大平板首层降加速度，贴牢"),
    _r("initial_layer_acceleration", "always", {"mul": 1.0}, "首层加速度跟随模式档", priority=99),
    _r("travel_acceleration", "slender_gt_2_5", {"mul": 0.88},
       "细高件空走降加速度"),
    _r("travel_acceleration", "always", {"mul": 1.0}, "空走加速度跟随模式档", priority=99),
    _r("default_acceleration", "slender_gt_2_5", {"mul": 0.9},
       "细高件整体降默认加速度"),
    _r("default_acceleration", "always", {"mul": 1.0}, "默认加速度跟随模式档", priority=99),
    _r("bridge_acceleration", "overhang_gt_0_22", {"mul": 0.85},
       "桥接降加速度，防断桥"),

    # ============================================================ Z 轴与补偿
    _r("xy_contour_compensation", "thin_lt_1_8", {"set": 0.02},
       "薄壁件给一点轮廓外扩，防壁厚偏薄", priority=10),
    _r("elefant_foot_compensation_layers", "small_footprint", {"min": 2},
       "底面小的件象脚补偿层数加到 2 层"),
    _r("elefant_foot_compensation_layers", "always", {"mul": 1.0},
       "象脚补偿层数跟随基准", priority=99),

    # ============================================================ 首层粘合
    _r("brim_type", "flat_lt_0_25", {"set": "auto_brim"},
       "大平板用自动裙边附着，比裙边压得住翘曲"),
    _r("brim_type", "small_footprint", {"set": "auto_brim"},
       "底面小的件用自动裙边扩大着地区"),
    _r("brim_type", "always", {"mul": 1.0}, "裙边类型按几何自动判断", priority=99),  # 不覆盖上层
    _r("brim_width", "flat_lt_0_25", {"mul": 1.0},
       "大平板裙边加宽到 8 mm"),
    _r("brim_width", "small_footprint", {"mul": 1.0},
       "小底面积件裙边加宽到 10 mm"),
    _r("brim_width", "always", {"mul": 1.0}, "裙边宽度由「裙边定量」层按倾覆指数决定", priority=99),
    _r("skirt_height", "flat_lt_0_25", {"min": 3},
       "大平板裙边层数加高"),
    _r("skirt_distance", "multi_object", {"min": 2},
       "多件同盘，裙边距离拉开"),
    _r("skirt_per_object", "multi_object", {"set": True},
       "多件同盘，每个对象单独裙边，避免互相影响"),
    _r("raft_layers", "flat_lt_0_15", {"min": 3},
       "超薄板加筏板，防翘曲"),
    _r("raft_contact_distance", "flat_lt_0_15", {"min": 0.2},
       "筏板与模型留 0.2 mm"),
    _r("raft_expansion", "flat_lt_0_15", {"min": 5},
       "筏板外扩 5 mm"),
    _r("raft_first_layer_density", "flat_lt_0_15", {"min": 40},
       "筏板首层加密到 40%"),
    _r("raft_first_layer_expansion", "flat_lt_0_15", {"min": 5},
       "筏板首层外扩 5 mm"),

    # ============================================================ 墙体高级
    _r("wall_loops", "slender_gt_2_5", {"min": 4},
       "细高件外壁加到 4 圈，底才不晃"),
    _r("wall_loops", "thin_lt_1_8", {"min": 3},
       "薄壁件保 3 圈"),
    _r("wall_loops", "always", {"mul": 1.0}, "外壁圈数跟随模式档", priority=99),
    _r("top_shell_layers", "always", {"mul": 1.0}, "顶层数跟随模式档", priority=99),
    _r("bottom_shell_layers", "flat_lt_0_25", {"min": 4},
       "大平板底层加厚，抗翘"),
    _r("bottom_shell_layers", "always", {"mul": 1.0}, "底层数跟随模式档", priority=99),
    _r("only_one_wall_top", "open_top", {"set": False},
       "开口件顶面不只打一圈墙，保强度"),
    _r("only_one_wall_first_layer", "small_lt_10cc", {"set": True},
       "小件首层只打一圈墙，细节不糊"),
    _r("only_one_wall_top", "always", {"mul": 1.0}, "顶面单墙按默认（不覆盖模式档）", priority=99),
    _r("detect_thin_wall", "thin_lt_1_8", {"set": True},
       "薄壁件开启薄壁检测"),
    _r("detect_overhang_wall", "overhang_gt_0_12", {"set": True},
       "悬垂面多，开启悬垂墙检测"),
    _r("precise_outer_wall", "open_top", {"set": True},
       "开口件外壁走线精确，轮廓更准"),
    _r("ensure_vertical_shell_thickness", "thin_lt_1_8", {"set": "enabled"},
       "薄壁件保证垂直外壳厚度"),
    _r("alternate_extra_wall", "solid_gt_0_55", {"set": True},
       "实心件交替加墙，均衡壁厚"),
    _r("monotonic_travel_into_wall", "open_top", {"set": 0.3},
       "开口件单调线延伸 30% 入墙，壁根更实"),
    _r("min_bead_width", "thin_lt_1_8", {"mul": 0.9},
       "薄壁件最小挤线宽度放宽"),
    _r("wall_sequence", "always", {"mul": 1.0}, "墙打印顺序内到外", priority=99),  # 不覆盖上层
    _r("wall_distribution_count", "multi_object", {"min": 3},
       "多件同盘，墙均匀分配数加到 3"),
    _r("wall_transition_angle", "flat_lt_0_25", {"min": 30},
       "大平板墙过渡角加大"),
    _r("wall_transition_length", "flat_lt_0_25", {"min": 4},
       "大平板墙过渡长度加大"),
    _r("wall_transition_filter_deviation", "flat_lt_0_25", {"min": 0.1},
       "大平板墙过渡偏差放宽"),
    _r("top_one_wall_type", "always", {"mul": 1.0}, "顶面单墙类型保持 top only", priority=99),  # 不覆盖上层

    # ============================================================ 接缝与斜切
    _r("seam_position", "open_top", {"set": "aligned"},
       "开口件接缝对齐，接缝落在不明显处"),
    _r("seam_position", "always", {"mul": 1.0}, "接缝位置按默认对齐", priority=99),  # 不覆盖上层
    _r("seam_gap", "thin_lt_1_8", {"mul": 0.6},
       "薄壁件接缝间隙收紧，防漏"),
    _r("seam_gap", "always", {"mul": 1.0}, "接缝间隙跟随模式档", priority=99),
    _r("seam_placement_away_from_overhangs", "overhang_gt_0_12", {"set": True},
       "接缝避开悬垂面，悬垂面更干净"),
    _r("seam_slope_type", "flat_lt_0_25", {"set": "none"},
       "大平板不启用斜切（贴合更好）"),
    _r("seam_slope_type", "always", {"mul": 1.0}, "斜切类型默认关闭", priority=99),  # 不覆盖上层
    _r("seam_slope_conditional", "always", {"mul": 1.0}, "斜切仅用于外露，默认关（不覆盖模式档）", priority=99),
    _r("seam_slope_entire_loop", "always", {"mul": 1.0}, "斜切覆盖整圈，默认关（不覆盖模式档）", priority=99),
    _r("seam_slope_gap", "always", {"mul": 1.0}, "斜切间隙跟随模式档", priority=99),
    _r("seam_slope_min_length", "always", {"mul": 1.0}, "斜切最小长度跟随模式档", priority=99),
    _r("seam_slope_start_height", "always", {"mul": 1.0}, "斜切起始高度跟随模式档", priority=99),
    _r("seam_slope_steps", "always", {"mul": 1.0}, "斜切层数跟随模式档", priority=99),
    _r("seam_slope_inner_walls", "thin_lt_1_8", {"set": False},
       "薄壁件不做内壁斜切"),
    _r("scarf_angle_threshold", "flat_lt_0_25", {"min": 155},
       "大平板斜切角度阈值放宽"),

    # ============================================================ 熨烫
    _r("ironing_type", "flat_lt_0_25", {"set": "no ironing"},
       "大平板不熨烫（熨烫易翘边）"),
    _r("ironing_type", "always", {"mul": 1.0}, "熨烫类型默认关", priority=99),  # 不覆盖上层
    _r("ironing_pattern", "flat_lt_0_25", {"set": "rectilinear"},
       "熨烫图案用 rectilinear"),
    _r("ironing_flow", "always", {"mul": 1.0}, "熨烫流量跟随模式档", priority=99),
    _r("ironing_spacing", "flat_lt_0_25", {"min": 0.1},
       "大平板熨烫间距收紧"),
    _r("ironing_speed", "flat_lt_0_25", {"mul": 0.9},
       "大平板熨烫降速"),
    _r("ironing_inset", "always", {"mul": 1.0}, "熨烫内缩跟随模式档", priority=99),

    # ============================================================ 擦料塔
    _r("enable_prime_tower", "multi_object", {"set": True},
       "多件同盘开擦料塔，各件之间不互相拉丝"),
    _r("enable_prime_tower", "always", {"mul": 1.0}, "擦料塔默认按用户设置（不覆盖模式档）", priority=99),
    _r("prime_tower_width", "always", {"mul": 1.0}, "擦料塔宽度跟随基准", priority=99),
    _r("prime_tower_brim_width", "always", {"mul": 1.0}, "擦料塔底座宽度跟随基准", priority=99),
]


# ------------------------------------------------------------------ 应用

def _merge_into(dst: dict, key: str, op: dict, placeholder: bool = False) -> None:
    """把一条 op 合进结果（同类操作取更保守的一侧）。

    ``placeholder=True`` 表示这条是 priority>=99 的「跟随基准」占位规则。
    占位规则**不能覆盖**前面几何规则已经给出的绝对值（set）——
    否则「多件同盘开擦料塔」会被占位规则翻回 False。
    """
    if key not in dst:
        dst[key] = dict(op)
        return
    a, b = dst[key], op
    out = dict(a)
    if "mul" in a and "mul" in b:
        out["mul"] = float(a["mul"]) * float(b["mul"])
    if "set" in a and "set" in b:
        if placeholder:
            # 占位规则让位：保留几何规则给出的值
            pass
        else:
            try:
                av, bv = float(a["set"]), float(b["set"])
                # set 不确定方向时取更小的数值（更保守）
                out["set"] = min(av, bv)
            except (TypeError, ValueError):
                pass
    elif "set" in b and not placeholder:
        out["set"] = b["set"]
    if "min" in a or "min" in b:
        out["min"] = max(float(a.get("min", -1e18)), float(b.get("min", -1e18)))
    if "max" in a or "max" in b:
        out["max"] = min(float(a.get("max", 1e18)), float(b.get("max", 1e18)))
    if "add" in a and "add" in b:
        out["add"] = max(float(a["add"]), float(b["add"]))
    dst[key] = out


def apply(ctx: GeomCtx, mode: str = "balanced",
          rules: list[Rule] | None = None) -> tuple[dict, list[str]]:
    """按几何事实算出参数动作。

    返回 (ops, 说明列表)。说明里逐条写清「哪个几何特征 → 哪个参数 → 怎么调」。
    """
    rules = rules if rules is not None else RULES
    ops: dict[str, dict] = {}
    hits: dict[str, list[str]] = {}

    # 模式族：精细/超精细命中质量族规则，草稿命中均衡族规则
    hit_modes = set(modes_registry.group_members(mode))
    fam = modes_registry.family(mode)
    hit_modes.add(fam)

    ordered = sorted(range(len(rules)), key=lambda i: (rules[i].priority, i))
    for i in ordered:
        rule = rules[i]
        if rule.modes and mode not in rule.modes and not (set(rule.modes) & hit_modes):
            continue
        fn = CONDS.get(rule.cond)
        if fn is None or not fn(ctx):
            continue
        _merge_into(ops, rule.key, rule.op, placeholder=(rule.priority >= 99))
        hits.setdefault(rule.key, []).append(rule.reason)

    notes: list[str] = []
    if hits:
        # 只把「真被几何特征触发」的参数写进说明（mul=1 的占位规则不写）
        real = []
        for key, reasons in hits.items():
            if not any(r for r in reasons if r and "跟随" not in r and "基准" not in r):
                continue
            real.append(f"{key}（{'；'.join(dict.fromkeys(reasons))}）")
        if real:
            notes.append("按模型几何细调：" + "；".join(real) + "。")
    return ops, notes


def rule_table() -> list[dict]:
    """给 UI 看的规则表。"""
    out = []
    for r in RULES:
        out.append({
            "key": r.key,
            "cond": r.cond,
            "cond_desc": COND_DESC.get(r.cond, r.cond),
            "op": r.op,
            "reason": r.reason,
            "modes": list(r.modes),
            "priority": r.priority,
        })
    return out


def to_json_rules() -> list[dict]:
    """把内置规则导成 JSON 列表（写进规则库，用户可编辑）。"""
    return [
        {
            "key": r.key,
            "cond": r.cond,
            "op": r.op,
            "reason": r.reason,
            "modes": list(r.modes),
            "priority": r.priority,
        }
        for r in RULES
    ]


def parse_rules(raw: list[dict] | None) -> list[Rule] | None:
    """把规则库里的 JSON 列表解析成 Rule 对象。返回 None 表示用内置表。"""
    if not raw:
        return None
    out: list[Rule] = []
    for item in raw:
        try:
            out.append(Rule(
                key=str(item["key"]),
                cond=str(item.get("cond", "always")),
                op=dict(item.get("op") or {}),
                reason=str(item.get("reason", "")),
                modes=tuple(item.get("modes") or ()),
                priority=int(item.get("priority", 0)),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out or None


#: 条件的中文说明（UI 展示用）
COND_DESC: dict[str, str] = {
    "always": "总是",
    "never": "从不",
    "slender_gt_2_5": "模型细高比 ≥ 2.5",
    "slender_gt_4": "模型细高比 ≥ 4",
    "flat_lt_0_25": "模型扁平度 < 0.25（大平板）",
    "flat_lt_0_15": "模型扁平度 < 0.15（超薄板）",
    "thin_lt_1_8": "平均壁厚 < 1.8 mm（薄壁/镂空）",
    "thin_lt_1_2": "平均壁厚 < 1.2 mm（极薄）",
    "solid_gt_0_55": "填充率 > 0.55（实心厚件）",
    "open_top": "顶面封闭度 < 0.15（开口容器）",
    "narrow_neck": "中段宽度 / 最大宽度 < 0.6（细腰）",
    "long_bar": "平面长宽比 < 0.45（细长条）",
    "overhang_gt_0_12": "悬垂面占比 ≥ 12%",
    "overhang_gt_0_22": "悬垂面占比 ≥ 22%",
    "overhang_lt_0_05": "悬垂面占比 < 5%",
    "tall_gt_90": "模型高度 ≥ 90 mm",
    "tall_gt_160": "模型高度 ≥ 160 mm",
    "small_lt_10cc": "单件体积 < 10 cm³",
    "big_gt_60cc": "单件体积 > 60 cm³",
    "multi_object": "盘面多于 1 个对象",
    "not_on_plate": "模型没有贴着平台",
    "small_footprint": "底面总接触面积 < 1500 mm²",
    "small_detail": "盘面多件且每件都小（单件 < 20 cm³）",
}
