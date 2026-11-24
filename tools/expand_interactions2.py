"""第三轮规则补充：Jerk 全套、熨烫风扇、支撑接触面速度、筏板、擦料塔精调、流量开关。

补完后，剩下「从不改变」的只有三类：
  · 型号/机型专属开关（共形填充、互锁梁、H2D 分段互锁、AMS 槽位）
  · 由耗材或软件自动管理的元数据（收缩系数曲线、颜色渗透层、flush 倍率）
  · 用户按需手动开的特效（磨砂皮肤、螺旋模式、筏板、支撑熨烫）
这三类在界面上都会给出推荐值与「什么情况下该自己调」的说明。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import rules_engine   # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"

# Jerk 按机型分组：Bambu 官方 X1/P1/P2 都是 9，A1 系也 9，但入门机要压
JERK_BY_PRINTER = {
    "X1": {"default_jerk": 9, "outer_wall_jerk": 9, "inner_wall_jerk": 9,
           "infill_jerk": 9, "top_surface_jerk": 9, "initial_layer_jerk": 9,
           "travel_jerk": 9},
    "P1": {"default_jerk": 9, "outer_wall_jerk": 9, "inner_wall_jerk": 9,
           "infill_jerk": 9, "top_surface_jerk": 9, "initial_layer_jerk": 9,
           "travel_jerk": 9},
    "P2": {"default_jerk": 9, "outer_wall_jerk": 9, "inner_wall_jerk": 9,
           "infill_jerk": 9, "top_surface_jerk": 9, "initial_layer_jerk": 9,
           "travel_jerk": 9},
    "A1": {"default_jerk": 8, "outer_wall_jerk": 7, "inner_wall_jerk": 8,
           "infill_jerk": 8, "top_surface_jerk": 7, "initial_layer_jerk": 6,
           "travel_jerk": 8},
}


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8-sig"))
    have = {it["id"] for it in rules["interactions"]}

    def add(item: dict) -> None:
        if item["id"] not in have:
            rules["interactions"].append(item)
            have.add(item["id"])

    # ---- Jerk：按机型分组设
    for group, vals in JERK_BY_PRINTER.items():
        add({
            "id": f"jerk-{group.lower()}",
            "when": {"printer_group": group},
            "set": vals,
            "warn": (f"{group} 组 Jerk 按官方机器预设：{vals['default_jerk']} mm/s。"
                     "改高会加剧振纹，改低会拖慢转弯；这是官方验证过的平衡点。")
            if group == "A1" else "",
        })

    # ---- 熨烫风扇：熨烫时关风扇防骤冷
    add({
        "id": "ironing-fan-off",
        "when": {"mode": "quality"},
        "set": {"ironing_fan_speed": 0, "ironing_direction": 45},
        "warn": "熨烫时风扇设为 0：熨烫头需要在半熔状态下抹平，吹风会让表面发白。",
    })

    # ---- 支撑接触面速度与熨烫：拆得干净
    add({
        "id": "support-interface-slow",
        "when": {"mode": "quality"},
        "set": {
            "support_interface_speed": 80,
            "support_interface_loop_pattern": True,
            "support_interface_not_for_body": True,
            "support_object_skip_flush": True,
            "enforce_support_layers": 2,
            "independent_support_layer_height": True,
            "support_angle": 0,
            "tree_support_branch_distance": 5,
            "tree_support_branch_diameter_angle": 5,
        },
        "warn": "支撑接触面降到 80 mm/s 并加环绕：接触面平整、拆下来不留疤。",
    })

    # ---- 筏板默认关，给出「什么时候该开」
    add({
        "id": "raft-off-hint",
        "when": {"filament": "PLA"},
        "set": {
            "raft_layers": 0,
            "raft_contact_distance": 0.1,
            "raft_first_layer_density": 90,
            "raft_expansion": 1.5,
            "raft_first_layer_expansion": -1,
        },
        "warn": "筏板默认关闭（0 层）：只有小接触面高件或严重翘边的料才需要。"
                "真要开就在 Bambu Studio 里把「筏板层数」设为 2，其余参数已配好。",
    })

    # ---- 擦料塔精调
    add({
        "id": "tower-fine",
        "when": {"filament": "PLA"},
        "set": {
            "prime_tower_brim_width": 3,
            "prime_tower_lift_speed": 90,
            "prime_tower_fillet_wall": True,
            "prime_tower_flat_ironing": True,
            "prime_tower_extra_rib_length": 0,
            "prime_tower_enable_framework": False,
            "prime_volume_mode": "Default",
            "flush_multiplier": 1.0,
            "flush_multiplier_fast": 1.2,
            "enable_tower_interface_features": False,
            "wipe_tower_rotation_angle": 0,
        },
        "warn": "擦料塔细项：圆角墙 + 平面熨烫让塔更容易整块剥落；废料倍率保持 1.0（省料且不堵）。",
    })

    # ---- 流量与压力提前开关（按机型能力）
    add({
        "id": "pa-x1-p2",
        "when": {"printer_group": "X1"},
        "set": {"enable_pressure_advance": True, "adaptive_pressure_advance": True,
                "adaptive_pressure_advance_overhangs": True,
                "print_flow_ratio": 1.0, "volumetric_speed_coefficients": 1.0},
        "warn": "X1 系列热端支持压力提前自动标定：保持开启，悬垂处也自适应，转角不会堆料。",
    })
    add({
        "id": "pa-p2",
        "when": {"printer_group": "P2"},
        "set": {"enable_pressure_advance": True, "adaptive_pressure_advance": True,
                "adaptive_pressure_advance_overhangs": True,
                "print_flow_ratio": 1.0, "volumetric_speed_coefficients": 1.0},
        "warn": "P2 平台同样支持压力提前自适应，保持开启。",
    })

    # ---- 走线顺序与接缝细节
    add({
        "id": "seam-detail-quality",
        "when": {"mode": "quality"},
        "set": {
            "seam_slope_entire_loop": False,
            "seam_slope_gap": 0,
            "seam_slope_min_length": 10,
            "seam_slope_start_height": 10,
            "role_base_wipe_speed": True,
            "start_end_points": "auto",
        },
        "warn": "斜切只在最需要的位置做（不做整圈、最小长度 10 mm）：整圈斜切会让接缝变成一条长疤。",
    })

    # ---- 首层粘合补充
    add({
        "id": "first-layer-adhesion",
        "when": {"filament": "PLA"},
        "set": {"skirt_height": 1, "skirt_per_object": True, "brim_object_gap": 0,
                "initial_layer_infill_line_width": 0.5},
        "warn": "首层裙边高度 1 层、间隙 0：既能看清挤出是否正常，又不会浪费材料。",
    })

    # ---- 速度补充：过悬垂降速与桥接
    add({
        "id": "speed-bridge-overhang",
        "when": {"mode": "quality"},
        "set": {
            "enable_overhang_speed": True,
            "overhang_totally_speed": 20,
            "internal_bridge_support_thickness": 1.0,
            "max_bridge_length": 0,
            "bridge_no_support": False,
            "counterbore_hole_bridging": "partially_filtered",
            "small_perimeter_threshold": 3,
        },
        "warn": "悬垂全塌区速度压到 20 mm/s、内部桥接加厚到 1.0 mm；小周长阈值 3 mm（小于它的环自动降速）。",
    })

    # ---- 质量组补充
    add({
        "id": "quality-misc",
        "when": {"mode": "quality"},
        "set": {
            "min_layer_height": 0.08,
            "max_layer_height": 0.24,
            "line_width": 0.42,
            "sparse_infill_line_width": 0.45,
            "support_line_width": 0.38,
            "ooze_prevention": False,
            "print_in_clockwise": False,
            "print_sequence": "by layer",
            "avoid_crossing_wall_includes_support": False,
            "enable_order_independent_overlap_carving": True,
            "initial_layer_print_height": 0.2,
        },
        "warn": "质量附加项：支撑线宽收窄到 0.38 mm（好拆）、开启顺序无关重叠切割、"
                "打印顺序保持逐层（按对象打印只适合小批量同款）。",
    })

    # ---- Jerk 之外的加速度补充
    add({
        "id": "accel-first-layer-travel",
        "when": {"printer_group": "A1"},
        "set": {"initial_layer_travel_acceleration": 3000},
        "warn": "A1 系列首层空走加速度压到 3000：床身运动时有助于减少首层错位。",
    })
    add({
        "id": "accel-first-layer-travel-x1",
        "when": {"printer_group": "X1"},
        "set": {"initial_layer_travel_acceleration": 6000},
        "warn": "",
    })

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    eng = rules_engine.RulesEngine(rules)
    problems = eng.validate()
    print(f"交叉规则共 {len(rules['interactions'])} 条")
    if problems:
        print("自检问题：")
        for p in problems:
            print("  ⚠", p)
        return 1
    print("自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
