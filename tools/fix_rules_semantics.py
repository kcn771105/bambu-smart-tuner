"""一次性脚本：按 ground truth 修正规则库的语义问题（B1~B5）。

改动分四类：

  1. PRESERVE_KEYS  —— 用户实测标定值，defaults 层不再覆盖：
        收缩/孔洞补偿系数、耗材体积流量上限、流量自适应系数向量、
        擦料塔盘面位置、AMS 槽位、方向偏好、墙生成器等。
  2. FOLLOW_KEYS   —— 官方语义是「跟随默认加速度」/「不启用」，
        不能当绝对数值写：
        inner_wall_acceleration（官方恒 0）、sparse_infill_acceleration（官方恒 100%）、
        overhang_1_4_speed（官方 0 表示不启用）。
  3. 区间修正     —— schema 里声明的区间与官方实际取值范围对齐。
  4. 幽灵键处理   —— 官方预设里根本不存在的键，从 defaults 里移除，
        改成「工程里有才写」（soft）。

跑法：python tools/fix_rules_semantics.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema  # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"

# ------------------------------------------------------------------ 1. 保留用户值

PRESERVE_KEYS = [
    # 收缩/孔洞补偿：用户按自己喷嘴标定的小数，不能被默认值覆盖
    "counter_coef_1", "counter_coef_2", "counter_coef_3",
    "counter_limit_max", "counter_limit_min",
    "hole_coef_1", "hole_coef_2", "hole_coef_3",
    "hole_limit_max", "hole_limit_min",
    # 热端流量上限：用户按自己热端标定
    "filament_max_volumetric_speed",
    # 流量自适应系数：6 元素向量，用户/厂商标定
    "volumetric_speed_coefficients",
    # 盘面摆位：用户自己摆的擦料塔位置
    "wipe_tower_x", "wipe_tower_y",
    # AMS 槽位：0 = 不指定，用户可能没接 AMS
    "wall_filament", "support_filament", "support_interface_filament",
    # 打印方向偏好 / 结构开关：属于用户的显式选择
    "print_in_clockwise", "infill_combination", "reduce_crossing_wall",
    "wall_generator", "xy_hole_compensation",
    "brim_object_gap", "brim_width",
    # 抬升阈值：用户在特定高度机台上手调过
    "retract_lift_below", "retract_lift_above",
    # 速度平滑：用户按体感调过
    "smooth_coefficient",
]

# ------------------------------------------------------------------ 2. 跟随语义键
# 官方语义：0 / "100%" = 不写绝对值，跟随默认。引擎对这些键只做「保持原值」。

FOLLOW_KEYS = [
    "inner_wall_acceleration",       # 官方恒 ["0","0"] = 跟随 default_acceleration
    "sparse_infill_acceleration",    # 官方恒 ["100%","100%","100%"] = 跟随
    "overhang_1_4_speed",            # 官方 0 = 不启用该档
]

# ------------------------------------------------------------------ 3. 幽灵键
# 官方预设 + 真实工程里都不存在的键：defaults 层不给值，
# 只有工程本身有这个键时才参与（soft）。

GHOST_KEYS = [
    "top_bottom_infill_wall_overlap", "gap_fill_speed", "wipe_tower_bridging",
    "internal_solid_infill_acceleration", "bridge_acceleration", "z_offset",
    "elefant_foot_compensation_layers", "support_density",
    "adaptive_pressure_advance", "adaptive_pressure_advance_overhangs",
    "friction_compensation", "resonance_avoidance",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
]


def main() -> None:
    data = json.loads(RULES.read_text(encoding="utf-8"))

    removed_defaults: list[str] = []
    removed_printer: list[str] = []
    removed_filament: list[str] = []
    removed_mode: list[str] = []
    removed_inter: list[str] = []

    # ---- defaults 层：去掉保留键、跟随键、幽灵键
    defaults = data["defaults"]
    for k in PRESERVE_KEYS + FOLLOW_KEYS + GHOST_KEYS:
        if defaults.pop(k, None) is not None:
            removed_defaults.append(k)

    # ---- 机型基线层：去掉保留键与跟随键
    for pk, pn in data["printers"].items():
        base = pn.get("baseline", {})
        for k in PRESERVE_KEYS + FOLLOW_KEYS:
            if base.pop(k, None) is not None:
                removed_printer.append(f"{pk}.{k}")

    # ---- 耗材基线层：去掉保留键与跟随键
    for fk, fn in data["filaments"].items():
        base = fn.get("baseline", {})
        for k in PRESERVE_KEYS + FOLLOW_KEYS:
            if base.pop(k, None) is not None:
                removed_filament.append(f"{fk}.{k}")
        for mk, mo in (fn.get("mode_ops") or {}).items():
            for k in PRESERVE_KEYS + FOLLOW_KEYS:
                if mo.pop(k, None) is not None:
                    removed_filament.append(f"{fk}.mode_ops.{mk}.{k}")

    # ---- 模式层：去掉保留键与跟随键
    for mk, mn in data["modes"].items():
        ops = mn.get("ops", {})
        for k in PRESERVE_KEYS + FOLLOW_KEYS:
            if ops.pop(k, None) is not None:
                removed_mode.append(f"{mk}.{k}")

    # ---- 交叉规则层：去掉保留键与跟随键
    for it in data["interactions"]:
        for sect in ("set", "ops"):
            m = it.get(sect) or {}
            for k in PRESERVE_KEYS + FOLLOW_KEYS:
                if m.pop(k, None) is not None:
                    removed_inter.append(f"{it.get('id')}.{sect}.{k}")

    # ----  jerk 键：官方没有 jerk 键族（Bambu 用 machine_max_jerk_*），
    #       全部从规则库里撤掉，改由 schema 的「soft + 不在 defaults」表达。
    jerk_removed: list[str] = []
    all_jerk = [k for k in schema.PARAMS if k.endswith("_jerk")]
    for k in all_jerk:
        if defaults.pop(k, None) is not None:
            jerk_removed.append(f"defaults.{k}")
    for pk, pn in data["printers"].items():
        for k in all_jerk:
            if pn.get("baseline", {}).pop(k, None) is not None:
                jerk_removed.append(f"printers.{pk}.{k}")
    for fk, fn in data["filaments"].items():
        for k in all_jerk:
            if fn.get("baseline", {}).pop(k, None) is not None:
                jerk_removed.append(f"filaments.{fk}.{k}")
    for mk, mn in data["modes"].items():
        for k in all_jerk:
            if mn.get("ops", {}).pop(k, None) is not None:
                jerk_removed.append(f"modes.{mk}.{k}")
    for it in data["interactions"]:
        for sect in ("set", "ops"):
            for k in all_jerk:
                if (it.get(sect) or {}).pop(k, None) is not None:
                    jerk_removed.append(f"{it.get('id')}.{sect}.{k}")

    # ---- 写回
    RULES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"defaults 层移除 {len(removed_defaults)} 个键")
    print(f"  {removed_defaults}")
    print(f"机型基线移除 {len(removed_printer)} 个：{removed_printer}")
    print(f"耗材基线移除 {len(removed_filament)} 个：{removed_filament}")
    print(f"模式层移除 {len(removed_mode)} 个：{removed_mode}")
    print(f"交叉规则移除 {len(removed_inter)} 个：{removed_inter}")
    print(f"jerk 键移除 {len(jerk_removed)} 个：{jerk_removed}")
    print(f"规则库现在 {len(data['defaults'])} 条 defaults，{RULES.stat().st_size} bytes")


if __name__ == "__main__":
    main()
