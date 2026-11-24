"""参数表（schema）

这里声明本程序允许写入 Bambu Studio 工程文件的所有切片参数，以及每个参数的：

  key            Bambu Studio / Orca 系工程里 `Metadata/project_settings.config` 的键名
  label          中文名，UI 与报告里显示
  group          分组，决定 UI 表格分节与报告分节
  kind           值类型，决定写回 3mf 时的字符串格式
  vmin / vmax    Bambu Studio 界面允许的合法区间；越界会被切片器拒绝或静默改值
  soft           True = 该键在部分机型/版本里不存在，只有工程里已有该键时才写
  nozzle_scaled  True = 区间与喷嘴直径线性相关（层高、线宽），运行时按喷嘴收紧

参数值在内存里统一用 float / int / str / bool 表示，写回 3mf 时由
`format_value()` 还原成 Bambu Studio 期望的字符串（含 "15%"、[0.8] 这类写法）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

FLOAT = "float"
INT = "int"
PCT = "pct"            # 写成 "15%"
PCT_NUM = "pct_num"    # 写成 "100"（风扇这类 0-100 的纯数字）
ENUM = "enum"
BOOL = "bool"
ARRAY_FLOAT = "array_float"   # 写成 ["0.8"]，按耗材槽位复制
ARRAY_PCT = "array_pct"       # 写成 ["50%"]，按耗材槽位复制
ENUM_ARRAY = "enum_array"     # 写成 ["uniform_cooling"]
VEC_FLOAT = "vec_float"       # 空格分隔的向量，写成 ["0 0 0 0 0 0"]

NUMERIC_KINDS = (FLOAT, INT, PCT, PCT_NUM, ARRAY_FLOAT, ARRAY_PCT)
ARRAY_KINDS = (ARRAY_FLOAT, ARRAY_PCT, ENUM_ARRAY, VEC_FLOAT)
# 向量类参数写回时原样保留文本，不做标量数值化
VERBATIM_KINDS = (VEC_FLOAT,)

GROUPS: list[tuple[str, str]] = [
    ("quality", "质量与线宽"),
    ("wall", "墙体高级"),
    ("infill", "填充"),
    ("speed", "速度"),
    ("accel", "加速度"),
    ("jerk", "Jerk"),
    ("cooling", "冷却"),
    ("retraction", "回抽"),
    ("tower", "擦料塔"),
    ("z", "Z 轴与补偿"),
    ("seam", "接缝与斜切"),
    ("ironing", "熨烫"),
    ("support", "悬垂与支撑"),
    ("adhesion", "首层粘合"),
    ("flow", "流量 / 压力提前 / 振纹"),
]

GROUP_LABEL = dict(GROUPS)


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    group: str
    kind: str
    vmin: float
    vmax: float
    step: float = 1.0
    unit: str = ""
    choices: tuple[str, ...] = ()
    decimals: int = 2
    soft: bool = False
    nozzle_scaled: bool = False
    preserve: bool = False      # True = 保留用户实测标定值，不被规则库默认值覆盖

    @property
    def group_label(self) -> str:
        return GROUP_LABEL.get(self.group, self.group)


def P(key, label, group, kind, vmin, vmax, step=1.0, unit="", choices=(),
      decimals=2, soft=False, nozzle_scaled=False, preserve=False) -> ParamSpec:
    return ParamSpec(key, label, group, kind, float(vmin), float(vmax), step,
                     unit, tuple(choices), decimals, soft, nozzle_scaled, preserve)


SPARSE_PATTERNS = ("grid", "gyroid", "honeycomb", "cubic", "adaptive_cubic",
                   "lightning", "rectilinear", "concentric", "triangles",
                   "tri-hexagon", "3dhoneycomb", "aligned_rectilinear", "cross_hatch")
TOP_PATTERNS = ("monotonic", "monotonicline", "rectilinear", "concentric",
                "hilbertcurve", "archimedeanchords")
SOLID_PATTERNS = ("monotonic", "monotonicline", "rectilinear", "zig-zag", "concentric")
SUPPORT_BASE_PATTERNS = ("default", "grid", "rectilinear", "concentric", "honeycomb", "lightning")
SUPPORT_TYPES = ("tree(auto)", "normal(auto)", "tree(manual)", "normal(manual)")
SUPPORT_STYLES = ("default", "grid", "snug", "tree_slim", "tree_strong", "tree_hybrid")
BRIM_TYPES = ("auto_brim", "outer_only", "inner_only", "outer_and_inner", "no_brim")

_PARAM_LIST: list[ParamSpec] = [
    # ---------------- 质量与线宽 ----------------
    P("layer_height", "层高", "quality", FLOAT, 0.04, 0.6, 0.02, "mm", nozzle_scaled=True),
    P("initial_layer_print_height", "首层层高", "quality", FLOAT, 0.04, 0.6, 0.02, "mm", nozzle_scaled=True),
    P("line_width", "默认线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("outer_wall_line_width", "外壁线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("inner_wall_line_width", "内壁线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("internal_solid_infill_line_width", "内部实心线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("sparse_infill_line_width", "稀疏填充线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("top_surface_line_width", "顶面线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("initial_layer_line_width", "首层线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("support_line_width", "支撑线宽", "quality", FLOAT, 0.1, 2.0, 0.01, "mm", nozzle_scaled=True),
    P("wall_loops", "墙层数（外壁+内壁）", "quality", INT, 1, 10, 1, "圈"),
    P("top_shell_layers", "顶层层数", "quality", INT, 1, 10, 1, "层"),
    P("bottom_shell_layers", "底层层数", "quality", INT, 1, 10, 1, "层"),

    # ---------------- 填充 ----------------
    P("sparse_infill_density", "填充密度", "infill", PCT, 0, 100, 5, "%", decimals=0),
    P("sparse_infill_pattern", "填充图案", "infill", ENUM, 0, 0, 1, "", SPARSE_PATTERNS),
    P("top_surface_pattern", "顶面图案", "infill", ENUM, 0, 0, 1, "", TOP_PATTERNS),
    P("internal_solid_infill_pattern", "内部实心图案", "infill", ENUM, 0, 0, 1, "", SOLID_PATTERNS),
    P("infill_wall_overlap", "填充与墙重叠", "infill", PCT, 0, 50, 1, "%", decimals=0),
    P("top_bottom_infill_wall_overlap", "顶底与墙重叠", "infill", PCT, 0, 50, 1, "%", decimals=0),
    P("infill_direction", "填充走线角度", "infill", FLOAT, 0, 360, 5, "°", decimals=0),

    # ---------------- 速度 ----------------
    P("outer_wall_speed", "外壁速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("inner_wall_speed", "内壁速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("sparse_infill_speed", "稀疏填充速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("internal_solid_infill_speed", "内部实心速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("top_surface_speed", "顶面速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("initial_layer_speed", "首层速度", "speed", FLOAT, 5, 200, 5, "mm/s", decimals=0),
    P("initial_layer_infill_speed", "首层填充速度", "speed", FLOAT, 5, 300, 5, "mm/s", decimals=0),
    P("gap_infill_speed", "缝隙填充速度", "speed", ARRAY_FLOAT, 5, 500, 5, "mm/s", decimals=0),
    P("travel_speed", "空走速度", "speed", FLOAT, 50, 1000, 10, "mm/s", decimals=0),
    P("support_speed", "支撑速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),
    P("bridge_speed", "桥接速度", "speed", FLOAT, 5, 200, 5, "mm/s", decimals=0),
    P("overhang_1_4_speed", "悬垂 1/4 速度", "speed", FLOAT, 0, 300, 5, "mm/s", decimals=0),
    P("overhang_2_4_speed", "悬垂 2/4 速度", "speed", FLOAT, 0, 300, 5, "mm/s", decimals=0),
    P("overhang_3_4_speed", "悬垂 3/4 速度", "speed", FLOAT, 0, 300, 5, "mm/s", decimals=0),
    P("overhang_4_4_speed", "悬垂 4/4 速度", "speed", FLOAT, 0, 300, 5, "mm/s", decimals=0),
    P("enable_overhang_speed", "启用悬垂降速", "speed", BOOL, 0, 1),

    # ---------------- 冷却 ----------------
    # 注意：风扇/回抽/流量这几组在 Bambu Studio 里属于「耗材页」与「机器页」，
    # 本程序只读不改（见 core/scope.py）。soft=True 表示不参与 defaults 覆盖，
    # 实际写入还会被 scope 闸门二次拦住。
    P("fan_min_speed", "风扇最小转速", "cooling", PCT_NUM, 0, 100, 5, "%", decimals=0, soft=True),
    P("fan_max_speed", "风扇最大转速", "cooling", PCT_NUM, 0, 100, 5, "%", decimals=0, soft=True),
    P("overhang_fan_speed", "悬垂风扇转速", "cooling", PCT_NUM, 0, 100, 5, "%", decimals=0, soft=True),
    P("overhang_fan_threshold", "悬垂风扇触发阈值", "cooling", PCT, 0, 100, 5, "%", decimals=0, soft=True),
    P("close_fan_the_first_x_layers", "首 N 层不开风扇", "cooling", INT, 0, 10, 1, "层", soft=True),
    P("full_fan_speed_layer", "第 N 层起全速风扇", "cooling", INT, 0, 10, 1, "层", soft=True),
    P("additional_cooling_fan_speed", "辅助风扇转速", "cooling", PCT_NUM, 0, 100, 5, "%", decimals=0, soft=True),

    # ---------------- 回抽与擦嘴 ----------------
    P("retraction_length", "回抽距离", "retraction", ARRAY_FLOAT, 0, 10, 0.1, "mm", soft=True),
    P("retraction_speed", "回抽速度", "retraction", FLOAT, 1, 100, 1, "mm/s", decimals=0, soft=True),
    P("deretraction_speed", "回填速度", "retraction", FLOAT, 0, 100, 1, "mm/s", decimals=0, soft=True),
    P("retract_before_wipe", "擦嘴前回抽比例", "retraction", PCT, 0, 100, 5, "%", decimals=0, soft=True),
    P("retract_restart_extra", "重启动额外挤出", "retraction", FLOAT, -1, 2, 0.01, "mm", soft=True),
    P("retract_when_changing_layer", "换层回抽", "retraction", BOOL, 0, 1, soft=True),
    P("wipe", "擦嘴", "retraction", BOOL, 0, 1, soft=True),
    P("wipe_distance", "擦嘴距离", "retraction", FLOAT, 0, 10, 0.5, "mm", soft=True),
    P("retraction_minimum_travel", "最小回抽行程", "retraction", FLOAT, 0, 10, 0.5, "mm", soft=True),
    P("z_hop", "Z 抬升", "retraction", FLOAT, 0, 5, 0.05, "mm", soft=True),
    P("z_hop_types", "Z 抬升方式", "retraction", ENUM, 0, 0, 1, "",
      ("Auto Lift", "Normal Lift", "Spiral Lift", "Slope Lift"), soft=True),
    P("retract_lift_above", "仅高于此高度抬升", "retraction", FLOAT, 0, 400, 0.05, "mm", soft=True, preserve=True),
    P("retract_lift_below", "仅低于此高度抬升", "retraction", FLOAT, 0, 400, 0.05, "mm", soft=True, preserve=True),

    # ---------------- 擦料塔 ----------------
    P("enable_prime_tower", "启用擦料塔", "tower", BOOL, 0, 1),
    P("prime_tower_width", "擦料塔宽度", "tower", FLOAT, 20, 150, 5, "mm", decimals=0),
    P("wipe_tower_bridging", "擦料塔过渡长度", "tower", FLOAT, 0, 50, 1, "mm", decimals=0),
    P("wipe_tower_rotation_angle", "擦料塔旋转角", "tower", FLOAT, 0, 360, 5, "°", decimals=0, soft=True),
    P("prime_tower_brim_width", "擦料塔底座宽度", "tower", FLOAT, -1, 20, 1, "mm", decimals=0, soft=True),

    # ---------------- 加速度 ----------------
    # 注意：官方预设里 inner_wall_acceleration 恒为 0、sparse_infill_acceleration 恒为
    # "100%"，两者都表示「跟随 default_acceleration」。本程序不主动改写这两个键
    # （规则库里已撤掉），工程里原样保留。
    P("default_acceleration", "默认加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0),
    P("outer_wall_acceleration", "外壁加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0),
    P("inner_wall_acceleration", "内壁加速度（0=跟随）", "accel", FLOAT, 0, 20000, 100, "mm/s²", decimals=0, preserve=True),
    P("sparse_infill_acceleration", "稀疏填充加速度（100%=跟随）", "accel", FLOAT, 0, 20000, 100, "mm/s²", decimals=0, preserve=True),
    P("internal_solid_infill_acceleration", "内部实心加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0, soft=True),
    P("top_surface_acceleration", "顶面加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0),
    P("initial_layer_acceleration", "首层加速度", "accel", FLOAT, 100, 3000, 50, "mm/s²", decimals=0),
    P("travel_acceleration", "空走加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0),
    P("bridge_acceleration", "桥接加速度", "accel", FLOAT, 100, 20000, 100, "mm/s²", decimals=0, soft=True),

    # ---------------- Jerk ----------------
    P("default_jerk", "默认 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("outer_wall_jerk", "外壁 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("inner_wall_jerk", "内壁 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("infill_jerk", "填充 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("top_surface_jerk", "顶面 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("initial_layer_jerk", "首层 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),
    P("travel_jerk", "空走 Jerk", "jerk", FLOAT, 1, 30, 0.5, "mm/s", decimals=1),

    # ---------------- Z 轴与补偿 ----------------
    P("z_offset", "Z 偏移", "z", FLOAT, -2, 2, 0.01, "mm"),
    P("elefant_foot_compensation", "象脚 / 首层对齐补偿", "z", FLOAT, 0, 1, 0.01, "mm"),
    P("elefant_foot_compensation_layers", "象脚补偿层数", "z", INT, 0, 10, 1, "层", soft=True),
    P("reduce_crossing_wall", "减少外墙穿越", "z", BOOL, 0, 1),
    P("xy_hole_compensation", "孔洞 XY 补偿", "z", FLOAT, -0.5, 0.5, 0.01, "mm", soft=True),
    P("xy_contour_compensation", "轮廓 XY 补偿", "z", FLOAT, -0.5, 0.5, 0.01, "mm", soft=True),

    # ---------------- 悬垂与支撑 ----------------
    P("support_threshold_angle", "悬垂判定角", "support", FLOAT, 0, 90, 5, "°", decimals=0),
    P("support_density", "支撑密度", "support", PCT, 0, 100, 5, "%", decimals=0),
    P("support_top_z_distance", "支撑顶面分离间隙", "support", FLOAT, 0, 2, 0.01, "mm"),
    P("support_bottom_z_distance", "支撑底面分离间隙", "support", FLOAT, 0, 2, 0.01, "mm", soft=True),
    P("support_object_xy_distance", "支撑与模型 XY 间距", "support", FLOAT, 0, 5, 0.05, "mm"),
    P("support_interface_top_layers", "支撑接触层数", "support", INT, 0, 10, 1, "层"),
    P("support_base_pattern", "支撑主体图案", "support", ENUM, 0, 0, 1, "", SUPPORT_BASE_PATTERNS),
    P("support_type", "支撑类型", "support", ENUM, 0, 0, 1, "", SUPPORT_TYPES),
    P("support_style", "支撑样式", "support", ENUM, 0, 0, 1, "", SUPPORT_STYLES, soft=True),

    # ---------------- 流量 / 压力提前 / 振纹 ----------------
    # filament_flow_ratio / pressure_advance 属耗材页，只读不改。
    P("filament_flow_ratio", "流量比例", "flow", ARRAY_FLOAT, 0.5, 1.5, 0.01, "", soft=True),
    P("initial_layer_flow_ratio", "首层流量比例", "flow", FLOAT, 0.5, 1.5, 0.01, "", soft=True),
    P("pressure_advance", "压力提前", "flow", ARRAY_FLOAT, 0, 0.5, 0.005, "", decimals=3, soft=True),
    P("enable_pressure_advance", "启用压力提前", "flow", BOOL, 0, 1, soft=True),
    P("adaptive_pressure_advance", "自适应压力提前", "flow", BOOL, 0, 1),
    P("adaptive_pressure_advance_overhangs", "悬垂自适应压力提前", "flow", BOOL, 0, 1),
    P("friction_compensation", "摩擦补偿", "flow", FLOAT, 0, 100, 1, "%", decimals=0, soft=True),
    P("resonance_avoidance", "振纹抑制（共振规避）", "flow", BOOL, 0, 1),
    P("min_resonance_avoidance_speed", "共振规避最低速度", "flow", FLOAT, 0, 500, 10, "mm/s", decimals=0, soft=True),
    P("max_resonance_avoidance_speed", "共振规避最高速度", "flow", FLOAT, 0, 500, 10, "mm/s", decimals=0, soft=True),

    # ---------------- 首层粘合 ----------------
    P("brim_type", "裙边类型", "adhesion", ENUM, 0, 0, 1, "", BRIM_TYPES),
    P("brim_width", "裙边宽度", "adhesion", FLOAT, 0, 30, 1, "mm", decimals=0, preserve=True),
    P("brim_object_gap", "裙边与模型间距", "adhesion", FLOAT, 0, 1, 0.01, "mm", preserve=True),
    P("raft_layers", "筏板层数", "adhesion", INT, 0, 10, 1, "层", soft=True),
]

PARAMS: dict[str, ParamSpec] = {p.key: p for p in _PARAM_LIST}


def _load_extra() -> None:
    """把第二批 / 第三批参数并进 PARAMS（同名不覆盖）。"""
    for mod_name, attr in (("schema_extra", "EXTRA_PARAMS"),
                           ("schema_extra3", "EXTRA_PARAMS_3"),
                           ("schema_extra4", "EXTRA_PARAMS_4")):
        try:
            mod = __import__(f"{__package__}.{mod_name}", fromlist=[attr]) \
                if __package__ else __import__(mod_name)
        except ImportError:          # 单独运行 schema.py 时忽略
            continue
        for row in getattr(mod, attr, []):
            # 行格式：(key,label,group,kind,vmin,vmax,step,unit,choices,decimals,soft[,preserve])
            preserve = bool(row[11]) if len(row) > 11 else False
            (key, label, group, kind, vmin, vmax, step, unit, choices, decimals, soft) = row[:11]
            if key in PARAMS:
                continue
            PARAMS[key] = ParamSpec(key, label, group, kind, float(vmin), float(vmax),
                                    step, unit, tuple(choices), decimals, soft,
                                    preserve=preserve)


_load_extra()


# ------------------------------------------------------------------ soft 扩展
# 以下几类键统一标成 soft（工程/机型里可能根本没有这个键，写回时按「有才写」处理）：
#
#   · PRESERVE  —— 用户实测标定值或用户的显式选择（收缩补偿、耗材流量上限、
#                  AMS 槽位、盘面摆位、打印方向、墙生成器、裙边…）
#   · FOLLOW    —— 官方语义是「跟随默认」（内壁/稀疏填充加速度）
#   · GHOST     —— 官方预设与真实工程里都不存在的键（属于「3mf 不存储、无法改」那一类）
#
# 它们的语义不是「必须有个基准值」，而是「不要乱动；只有规则明确要求时才改」。
SOFT_EXTRA_KEYS = {
    # 保留用户值
    "counter_coef_1", "counter_coef_2", "counter_coef_3",
    "counter_limit_max", "counter_limit_min",
    "hole_coef_1", "hole_coef_2", "hole_coef_3",
    "hole_limit_max", "hole_limit_min",
    "filament_max_volumetric_speed", "volumetric_speed_coefficients",
    "wipe_tower_x", "wipe_tower_y",
    "wall_filament", "support_filament", "support_interface_filament",
    "print_in_clockwise", "infill_combination", "reduce_crossing_wall",
    "wall_generator", "xy_hole_compensation",
    "brim_object_gap", "brim_width",
    "retract_lift_below", "retract_lift_above", "smooth_coefficient",
    # 跟随语义
    "inner_wall_acceleration", "sparse_infill_acceleration",
    # 官方不存在的键
    "top_bottom_infill_wall_overlap", "gap_fill_speed", "wipe_tower_bridging",
    "internal_solid_infill_acceleration", "bridge_acceleration", "z_offset",
    "elefant_foot_compensation_layers", "support_density",
    "adaptive_pressure_advance", "adaptive_pressure_advance_overhangs",
    "friction_compensation", "resonance_avoidance",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
}

# Bambu 官方没有 jerk 键族（用 machine_max_jerk_* 表达机器上限），这些键同样 soft
for _k in [k for k in list(PARAMS) if k.endswith("_jerk")]:
    SOFT_EXTRA_KEYS.add(_k)

for _k in SOFT_EXTRA_KEYS:
    _s = PARAMS.get(_k)
    if _s is not None and not _s.soft:
        PARAMS[_k] = ParamSpec(_s.key, _s.label, _s.group, _s.kind, _s.vmin, _s.vmax,
                               _s.step, _s.unit, _s.choices, _s.decimals, True,
                               _s.nozzle_scaled, _s.preserve)

# 耗材页 / 机器页的键统一标 soft —— 本程序只写切片工艺页（见 core/scope.py）。
# 它们的「上限值」仍会被 hardware.read() 读出来参与钳制，但一个字符都不改。
try:
    from .scope_data import SCOPE as _SCOPE  # type: ignore
except ImportError:      # 单独运行 schema.py 时忽略
    _SCOPE = {}
for _k, _sc in _SCOPE.items():
    if _sc in ("filament", "machine"):
        _s = PARAMS.get(_k)
        if _s is not None and not _s.soft:
            PARAMS[_k] = ParamSpec(_s.key, _s.label, _s.group, _s.kind, _s.vmin, _s.vmax,
                                   _s.step, _s.unit, _s.choices, _s.decimals, True,
                                   _s.nozzle_scaled, _s.preserve)


def spec(key: str) -> ParamSpec | None:
    return PARAMS.get(key)


def keys_in_group(group: str) -> list[str]:
    return [k for k, p in PARAMS.items() if p.group == group]


# ---------------------------------------------------------------- 值解析 / 格式化

#: 工程里「按热端变体分槽」的数组长度（print_extruder_variant 的条目数）。
#: 例：P2S 工程是 ["Direct Drive Standard","Direct Drive High Flow","Direct Drive E3D High Flow"]
#:     → 3 个槽位，outer_wall_speed 就是 ["200","500","500"]。
#: 这类键 Studio 显示的是「当前所选热端」那一槽的值，只改第 0 槽会出现
#: 「表里写了 124，Studio 里还是 500」——因为它读的是第 1 槽。
_VARIANT_SLOTS = 0

#: 分槽参数是否把所有槽位写成同一个值（默认写全，保证任何热端下都生效）
_WRITE_ALL_VARIANT_SLOTS = True


def set_variant_slots(n: int, *, write_all: bool | None = None) -> None:
    """告诉 schema：本工程的分槽参数有几个槽位（0 = 不知道，按单槽处理）。"""
    global _VARIANT_SLOTS, _WRITE_ALL_VARIANT_SLOTS
    _VARIANT_SLOTS = max(0, int(n or 0))
    if write_all is not None:
        _WRITE_ALL_VARIANT_SLOTS = bool(write_all)


def variant_slots() -> int:
    return _VARIANT_SLOTS



def _unwrap_slot(raw: Any) -> str:
    """把数组形态的原始值拆出第 0 槽（数组是 Bambu 按喷嘴/耗材分槽的写法）。

    工程里同一个键的形态并不固定：官方预设写 ["200","500","500"]，
    而同一段参数在另一些工程里写成标量 0.2。两种都要能读懂，
    所以解析时统一「先剥掉数组外壳，取第 0 槽」。
    """
    txt = str(raw).strip()
    if txt.startswith("["):
        try:
            arr = json.loads(txt)
        except (ValueError, TypeError):
            return txt
        if isinstance(arr, list) and arr:
            return str(arr[0]).strip()
    return txt


def _slot_texts(old_raw: Any) -> list[str]:
    """取回原始值的各槽位文本（标量形态时只有一个槽位）。"""
    txt = str(old_raw).strip() if old_raw is not None else ""
    if txt.startswith("["):
        try:
            arr = json.loads(txt)
        except (ValueError, TypeError):
            arr = None
        if isinstance(arr, list) and arr:
            return [str(x) for x in arr]
    return [txt] if txt else []


def parse_value(s: ParamSpec, raw: Any) -> Any:
    """把 project_settings.config 里的字符串解析成内存值。无法解析返回 None。

    数组型参数（["0.8"] / ["80%"] / ["uniform_cooling"]）统一取第 0 个槽位的值，
    因为本程序只按第一个耗材/喷嘴优化；写回时再按原数组长度复制。
    """
    if raw is None:
        return None
    if s.kind == VEC_FLOAT:
        # 向量参数（体积流量自适应系数）：官方写法是 ["0 0 0 0 0 0"]，
        # 是一整串空格分隔的数字，不是标量。整串原样保留。
        return str(raw).strip() or None
    txt = _unwrap_slot(raw)
    if s.kind in (ENUM,):
        return txt
    if s.kind == BOOL:
        return txt.strip().lower() in ("1", "true", "yes", "on")
    if s.kind == ENUM_ARRAY:
        return txt or None
    if s.kind in ARRAY_KINDS:
        try:
            while txt.endswith("%"):
                txt = txt[:-1].strip()
            return float(txt)
        except (ValueError, TypeError):
            return None
    # 标量数值：容忍 "15%" 这种写法（Bambu 的百分比键有时带 % 号）
    if txt.endswith("%"):
        txt = txt[:-1].strip()
    try:
        v = float(txt)
    except ValueError:
        return None
    if s.kind == INT:
        return int(round(v))
    return v


def format_value(s: ParamSpec, value: Any, old_raw: Any = None) -> str:
    """把内存值格式化成 Bambu Studio 期望的字符串。

    保持「原值是什么形态，就写回什么形态」：
      - 原值是数组 ["200","500","500"] → 写回 ["136","500","500"]
        （只改第 0 槽＝本次优化的喷嘴，其余槽位保持用户原值）
      - 原值是标量 0.2 → 写回 0.2

    数组型参数在 Bambu 里是按喷嘴/耗材分槽的，所以绝不能把优化值复制到
    所有槽位——那会把用户其它喷嘴的设定一起改掉。
    """
    slots = _slot_texts(old_raw)
    as_array = bool(slots) and str(old_raw).strip().startswith("[")
    n = len(slots) if slots else 1
    first = slots[0] if slots else ""

    if s.kind == BOOL:
        item = ("true" if bool(value) else "false") if first.strip().lower() in ("true", "false") \
            else ("1" if bool(value) else "0")
    elif s.kind in (ENUM, ENUM_ARRAY):
        item = str(value)
    elif s.kind == VEC_FLOAT:
        # 向量：整串保留（官方写法 ["0 0 0 0 0 0"]，元素本身是一整串文本）
        item = str(value).strip()
        if item.startswith("["):
            try:
                item = " ".join(str(x) for x in json.loads(item))
            except (ValueError, TypeError):
                item = item.strip("[]").strip()
    elif s.kind == PCT:
        v = numeric(value) or 0.0
        item = f"{int(round(v))}%" if abs(v - round(v)) < 1e-9 \
            else f"{v:.2f}".rstrip("0").rstrip(".") + "%"
    elif s.kind == ARRAY_PCT:
        # 数组里的百分比键（small_perimeter_speed / vertical_shell_speed），
        # 官方写法就是 ["50%"] —— 必须带 % 号
        v = numeric(value) or 0.0
        item = f"{int(round(v))}%" if abs(v - round(v)) < 1e-9 \
            else f"{v:.2f}".rstrip("0").rstrip(".") + "%"
    elif s.kind == PCT_NUM:
        item = str(int(round(numeric(value) or 0.0)))
    elif s.kind == INT:
        item = str(int(round(numeric(value) or 0.0)))
    else:                       # FLOAT / ARRAY_FLOAT
        v = numeric(value)
        if v is None:
            v = 0.0
        item = _fmt_float(v, s.decimals)
        # 原值带 % 号（官方用 "100%" 表示「跟随默认加速度」）→ 保持百分号写法
        if first.strip().endswith("%") and not item.endswith("%"):
            item = f"{item}%"

    if as_array:
        fill_all = (
            _WRITE_ALL_VARIANT_SLOTS
            and _VARIANT_SLOTS > 1
            and n == _VARIANT_SLOTS
            and s.kind != VEC_FLOAT      # 体积流量自适应系数是一整串数字，不按槽处理
        )
        if fill_all:
            # 按热端变体分槽：把同一个值写进每一槽，否则 Studio 里切到高流量热端
            # 会读第 1 槽、看起来「参数没变」
            out = [item] * n
        else:
            out = [item]
            out.extend(slots[1:n])
        return json.dumps(out, separators=(", ", ": "))
    return item


def _fmt_float(v: float, decimals: int) -> str:
    txt = f"{v:.{decimals}f}"
    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
    return txt or "0"


def numeric(value: Any) -> float | None:
    """把规则库里各种写法的数值统一成 float。

    规则库 JSON 里百分比常写成 "15%"、数组常写成 ["50%"]，
    这里统一把 % 去掉再转 float，失败返回 None。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if txt.startswith("[") and txt.endswith("]"):
        txt = txt[1:-1].strip()
        if "," in txt:
            txt = txt.split(",")[0].strip()
    txt = txt.rstrip("%").strip()
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def clamp(s: ParamSpec, value: float) -> float:
    if s.kind in (ENUM, BOOL, ENUM_ARRAY, VEC_FLOAT):
        return value
    v = min(max(float(value), s.vmin), s.vmax)
    if s.kind == INT:
        return round(v)
    return round(v, 6)


def display(s: ParamSpec, value: Any) -> str:
    """UI/报告里显示的值（带单位，不带内部格式）。"""
    if value is None:
        return "—"
    if s.kind == BOOL:
        return "开" if value else "关"
    if s.kind in (ENUM, ENUM_ARRAY):
        return str(value)
    if s.kind == VEC_FLOAT:
        return str(value)
    if s.kind == INT:
        return f"{int(value)} {s.unit}".strip()
    txt = _fmt_float(float(value), s.decimals)
    return f"{txt} {s.unit}".strip()
