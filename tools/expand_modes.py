"""扩展模式策略：让参数表里的可调项真正被规则用起来。

原则：
  · 只加「模式选择真的会改变它」的参数，不为了覆盖率而瞎改
  · 每组改动都对应一条可解释的工程理由（写进 note / desc）
  · 值取自本机 Bambu 官方预设的真实默认，改动幅度控制在保守范围

用法：python tools/expand_modes.py
（幂等：重复运行不会重复叠加，因为它直接覆盖 modes 节点）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import rules_engine   # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"


STRENGTH_OPS = {
    # ---- 结构强度主项
    "wall_loops": {"set": 4},
    "top_shell_layers": {"set": 5},
    "bottom_shell_layers": {"set": 4},
    "top_shell_thickness": {"set": 1.2},
    "bottom_shell_thickness": {"set": 0.8},
    "sparse_infill_density": {"set": 40},
    "sparse_infill_pattern": {"set": "gyroid"},
    "infill_wall_overlap": {"set": 22},
    "top_bottom_infill_wall_overlap": {"set": 20},
    "infill_combination": {"set": True},
    "top_surface_density": {"set": 100},
    "bottom_surface_density": {"set": 100},

    # ---- 线宽：加宽内壁换层间接触面积
    "outer_wall_line_width": {"mul": 1.05},
    "inner_wall_line_width": {"mul": 1.08},
    "internal_solid_infill_line_width": {"mul": 1.05},

    # ---- 速度：降外壁换粘合
    "outer_wall_speed": {"mul": 0.75},
    "outer_wall_acceleration": {"mul": 0.6},
    "inner_wall_acceleration": {"mul": 0.8},
    "sparse_infill_speed": {"mul": 0.95},
    "internal_solid_infill_speed": {"mul": 0.95},
    "initial_layer_speed": {"mul": 0.9},

    # ---- 冷却：降风扇提升层间结合力
    "fan_max_speed": {"mul": 0.85},
    "slow_down_for_layer_cooling": {"set": True},
    "slow_down_layer_time": {"mul": 1.2},

    # ---- 首层粘合
    "elefant_foot_compensation": {"set": 0.1},
    "brim_width": {"max": 8, "set": 7},
    "skirt_loops": {"set": 2},
    "skirt_distance": {"set": 3},

    # ---- 墙体细节
    "wall_generator": {"set": "arachne"},
    "detect_thin_wall": {"set": True},
    "ensure_vertical_shell_thickness": {"set": "ensure_all"},
    "precise_outer_wall": {"set": False},

    # ---- 接缝：强度优先不在意表面，用最近接缝省时间
    "seam_position": {"set": "nearest"},

    # ---- 桥接加强
    "bridge_flow": {"set": 1.05},
    "thick_bridges": {"set": True},

    # ---- Z 轴：不追求外观，正常补偿
    "xy_hole_compensation": {"set": 0.02},
}

QUALITY_OPS = {
    # ---- 层高与线宽
    "layer_height": {"mul": 0.75, "min": 0.08},
    "outer_wall_line_width": {"mul": 0.95},
    "top_surface_line_width": {"mul": 0.95},
    "initial_layer_line_width": {"mul": 0.98},
    "wall_loops": {"set": 3},
    "top_shell_layers": {"set": 5},
    "sparse_infill_density": {"mul": 0.85},
    "infill_wall_overlap": {"set": 12},

    # ---- 表面图案：单调走线
    "top_surface_pattern": {"set": "monotonic"},
    "internal_solid_infill_pattern": {"set": "monotonic"},
    "bottom_surface_pattern": {"set": "monotonic"},
    "sub_top_surface_pattern": {"set": "monotonic"},
    "top_surface_density": {"set": 100},

    # ---- 速度与加速度
    "outer_wall_speed": {"mul": 0.6},
    "top_surface_speed": {"mul": 0.8},
    "internal_solid_infill_speed": {"mul": 0.85},
    "gap_fill_speed": {"mul": 0.8},
    "small_perimeter_speed": {"set": 40},
    "vertical_shell_speed": {"set": 70},
    "outer_wall_acceleration": {"mul": 0.5},
    "top_surface_acceleration": {"mul": 0.6},
    "default_acceleration": {"mul": 0.85},
    "outer_wall_jerk": {"mul": 0.7},
    "top_surface_jerk": {"mul": 0.7},
    "travel_acceleration": {"mul": 0.8},
    "travel_short_distance_acceleration": {"mul": 0.7},
    "accel_to_decel_enable": {"set": True},
    "accel_to_decel_factor": {"set": 60},

    # ---- 接缝与斜切：把接缝藏起来
    "seam_position": {"set": "aligned_back"},
    "seam_slope_type": {"set": "external"},
    "seam_slope_conditional": {"set": True},
    "seam_slope_steps": {"set": 12},
    "seam_slope_inner_walls": {"set": True},
    "seam_gap": {"set": 10},
    "seam_placement_away_from_overhangs": {"set": True},
    "scarf_angle_threshold": {"set": 155},
    "apply_scarf_seam_on_circles": {"set": True},
    "wipe_speed": {"set": 70},

    # ---- 熨烫：顶面熨平（外观最大提升项）
    "ironing_type": {"set": "top"},
    "ironing_pattern": {"set": "monotonic"},
    "ironing_flow": {"set": 12},
    "ironing_spacing": {"set": 0.12},
    "ironing_speed": {"set": 25},
    "ironing_inset": {"set": 0.2},
    "ironing_direction": {"set": 45},

    # ---- 墙体
    "wall_generator": {"set": "arachne"},
    "precise_outer_wall": {"set": True},
    "detect_thin_wall": {"set": True},
    "monotonic_travel_into_wall": {"set": 30},
    "only_one_wall_top": {"set": False},

    # ---- 冷却：稳定表面
    "slow_down_for_layer_cooling": {"set": True},
    "no_slow_down_for_cooling_on_outwalls": {"set": False},
    "reduce_fan_stop_start_freq": {"set": True},

    # ---- 振纹抑制
    "resonance_avoidance": {"set": True},
    "min_resonance_avoidance_speed": {"set": 40},
    "max_resonance_avoidance_speed": {"set": 110},

    # ---- 桥接
    "bridge_flow": {"set": 1.0},
    "bridge_angle": {"set": 0},

    # ---- 首层与 Z
    "elefant_foot_compensation": {"set": 0.15},
    "elefant_foot_compensation_layers": {"set": 1},
    "only_one_wall_first_layer": {"set": False},
    "initial_layer_acceleration": {"mul": 0.8},

    # ---- 磨砂皮肤（默认关；想用自己开）
    "fuzzy_skin": {"set": "none"},

    # ---- 精度
    "slice_closing_radius": {"set": 0.049},
    "resolution": {"set": 0.01},
    "min_feature_size": {"set": 20},
    "enable_arc_fitting": {"set": True},

    # ---- 支撑接触面做细，拆得更干净
    "support_interface_spacing": {"set": 0.4},
    "support_interface_pattern": {"set": "grid"},
}

BALANCED_OPS = {
    "wall_loops": {"set": 3},
    "top_shell_layers": {"set": 4},
    "sparse_infill_density": {"mul": 1.35},
    "sparse_infill_pattern": {"set": "gyroid"},
    "infill_wall_overlap": {"set": 18},
    "outer_wall_speed": {"mul": 0.85},
    "outer_wall_acceleration": {"mul": 0.8},
    "top_surface_speed": {"mul": 0.9},
    "elefant_foot_compensation": {"set": 0.12},

    # 少量外观收益、几乎不花时间
    "seam_position": {"set": "aligned"},
    "seam_gap": {"set": 12},
    "wall_generator": {"set": "arachne"},
    "top_surface_pattern": {"set": "monotonic"},
    "top_surface_density": {"set": 100},
    "top_shell_thickness": {"set": 1.0},
    "infill_combination": {"set": True},
    "accel_to_decel_enable": {"set": True},
    "reduce_fan_stop_start_freq": {"set": True},
    "resonance_avoidance": {"set": True},

    # 窗帘：只叠了第一层，不做烫平
    "ironing_type": {"set": "no ironing"},
    "seam_slope_type": {"set": "none"},
}


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8-sig"))
    modes = rules["modes"]

    modes["strength"]["ops"] = STRENGTH_OPS
    modes["strength"]["desc"] = (
        "加厚墙体与壳层、提高填充密度换高强度图案、加宽内壁线宽、降外壁速度与加速度换层间粘合、"
        "降风扇减少层间温度差；熨烫关闭、接缝走最近位。允许打印时间上涨 20%~60%。")

    modes["quality"]["ops"] = QUALITY_OPS
    modes["quality"]["desc"] = (
        "降层高与线宽、外壁/顶面降速并降加速度与 Jerk、开启减速系数与振纹抑制、"
        "接缝用斜切藏在背面、顶面熨烫烫平、单调走线消除层纹。填充略降，外观优先。")

    modes["balanced"]["ops"] = BALANCED_OPS
    modes["balanced"]["desc"] = (
        "墙 +1、填充 +35% 换 gyroid、外壁降 15%、接缝对齐、开启减速系数与振纹抑制；"
        "不做熨烫与斜切。时间涨幅控制在 10%~25%。")

    # ---- 交叉规则补充：把形状/组合相关的可调项也用起来
    have = {it["id"] for it in rules["interactions"]}

    def add(item: dict) -> None:
        if item["id"] not in have:
            rules["interactions"].append(item)
            have.add(item["id"])

    add({
        "id": "strength-ironing-off",
        "when": {"mode": "strength"},
        "set": {"ironing_type": "no ironing", "seam_slope_type": "none"},
        "warn": "强度优先模式下熨烫与斜切都关掉：两者都会削弱表层与接缝的力学性能。",
    })
    add({
        "id": "tpu-no-ironing",
        "when": {"filament": "TPU"},
        "set": {"ironing_type": "no ironing", "seam_slope_type": "none",
                "spiral_mode": False},
        "warn": "TPU 不做熨烫与斜切：软料在熨烫时会堆积、斜切会拉丝。",
    })
    add({
        "id": "tpu-no-brim-gap",
        "when": {"filament": "TPU"},
        "set": {"brim_type": "outer_only", "brim_width": 6,
                "skirt_loops": 2, "initial_layer_speed": 20},
        "warn": "TPU 首层附着力强但易拉伸：用外侧裙边 + 更慢首层速度，避免边缘被扯起。",
    })
    add({
        "id": "abs-asa-no-fan",
        "when": {"filament": "ABS"},
        "set": {"fan_max_speed": 30, "slow_down_for_layer_cooling": True,
                "slow_down_layer_time": 15, "brim_type": "outer_only",
                "brim_width": 8, "draft_shield": "enabled"},
        "warn": "ABS 必须保温：风扇压到 30%、加长层冷却时间、开挡风罩、裙边加宽到 8 mm。",
    })
    add({
        "id": "asa-no-fan",
        "when": {"filament": "ASA"},
        "set": {"fan_max_speed": 40, "slow_down_for_layer_cooling": True,
                "slow_down_layer_time": 14, "brim_type": "outer_only",
                "brim_width": 8, "draft_shield": "enabled"},
        "warn": "ASA 收缩大：风扇压到 40%、开挡风罩、裙边 8 mm，大平面件建议加围挡。",
    })
    add({
        "id": "petg-stringing",
        "when": {"filament": "PETG"},
        "set": {"wipe": True, "wipe_distance": 2.5, "retract_before_wipe": 70,
                "travel_speed": 250, "seam_slope_type": "none"},
        "warn": "PETG 易拉丝：已加大擦嘴距离与擦嘴前回抽、压一档空走速度；斜切关闭（会挂料）。",
    })
    add({
        "id": "spiral-vase-hint",
        "when": {"mode": "quality", "filament": "PLA"},
        "set": {"spiral_mode": False},
        "warn": "单壁花瓶类模型请在 Bambu Studio 里手动开「螺旋花瓶模式」；"
                "本程序默认关闭——对实心件开启会得到空壳。",
    })
    add({
        "id": "big-nozzle-flow",
        "when": {"nozzle_ge": 0.6},
        "set": {"top_surface_density": 100, "bottom_surface_density": 100,
                "ironing_spacing": 0.2},
        "warn": "0.6 mm 以上喷嘴：走线宽，顶底必须打满 100% 才不会露填充；熨烫间距也相应加大。",
    })

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    # 校验
    eng = rules_engine.RulesEngine(rules)
    problems = eng.validate()
    print(f"模式已更新：strength {len(STRENGTH_OPS)} 项 / quality {len(QUALITY_OPS)} 项 / "
          f"balanced {len(BALANCED_OPS)} 项")
    print(f"交叉规则 {len(rules['interactions'])} 条")
    if problems:
        print("自检问题：")
        for p in problems:
            print("  ⚠", p)
        return 1
    print("自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
