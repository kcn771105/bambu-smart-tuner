"""第二轮规则补充：把支撑、冷却、擦料塔、回抽、Z 补偿里该随场景变的参数接进规则。

这一轮的取舍标准：
  · 支撑全部子参数 —— 支撑一开就要成套调，否则拆不下来
  · 冷却的风扇启停时序 —— 不同耗材差异大
  · 擦料塔 —— 单色/多色差别大
  · Z 补偿 —— 与机型、耗材收缩率相关
  · 保持不动 —— 共形填充、AMS 槽位、G 代码、收缩系数曲线、H2D 专属互锁
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import rules_engine   # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"


# 支撑成套参数：按「拆得下来 / 不塌」两个目标给三档
SUPPORT_PROFILES = {
    "none": {
        "enable_support": False,
    },
    "light": {
        "enable_support": True,
        "support_type": "tree(auto)",
        "support_style": "tree_slim",
        "support_threshold_angle": 40,
        "support_density": 10,
        "support_base_pattern": "default",
        "support_base_pattern_spacing": 2.5,
        "support_interface_top_layers": 2,
        "support_interface_bottom_layers": 2,
        "support_interface_spacing": 0.5,
        "support_interface_pattern": "auto",
        "support_top_z_distance": 0.22,
        "support_bottom_z_distance": 0.2,
        "support_object_xy_distance": 0.4,
        "support_object_first_layer_gap": 0.2,
        "support_expansion": 0,
        "support_critical_regions_only": True,
        "support_remove_small_overhang": True,
        "support_on_build_plate_only": False,
        "tree_support_branch_angle": 45,
        "tree_support_branch_diameter": 2,
    },
    "strong": {
        "enable_support": True,
        "support_type": "tree(auto)",
        "support_style": "tree_strong",
        "support_threshold_angle": 30,
        "support_density": 18,
        "support_base_pattern": "grid",
        "support_base_pattern_spacing": 2.0,
        "support_interface_top_layers": 3,
        "support_interface_bottom_layers": 3,
        "support_interface_spacing": 0.4,
        "support_interface_pattern": "grid",
        "support_top_z_distance": 0.2,
        "support_bottom_z_distance": 0.2,
        "support_object_xy_distance": 0.35,
        "support_object_first_layer_gap": 0.2,
        "support_expansion": 0.1,
        "support_critical_regions_only": False,
        "support_remove_small_overhang": False,
        "support_on_build_plate_only": False,
        "tree_support_branch_angle": 40,
        "tree_support_branch_diameter": 3,
        "tree_support_wall_count": 2,
    },
}


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8-sig"))
    have = {it["id"] for it in rules["interactions"]}

    def add(item: dict) -> None:
        if item["id"] not in have:
            rules["interactions"].append(item)
            have.add(item["id"])

    # ---- 支撑：默认关；只有模式/形状需要时成套打开
    add({
        "id": "support-default-off",
        "when": {"mode": "quality"},
        "set": SUPPORT_PROFILES["light"],
        "warn": "默认把支撑参数成套配好（树状 + 细枝 + 40° 阈值 + 2 层接触面）。"
                "模型真的需要支撑时才会生效；Bambu Studio 里勾上「启用支撑」即可直接用这套参数。",
    })
    add({
        "id": "support-strength",
        "when": {"mode": "strength"},
        "set": SUPPORT_PROFILES["strong"],
        "warn": "强度优先：支撑按「不塌」配（网格主体 + 3 层接触面 + 18% 密度），拆起来会稍费劲。",
    })

    # ---- 冷却时序：不同耗材风扇启停差别很大
    add({
        "id": "cooling-pla-fast",
        "when": {"filament": "PLA"},
        "set": {
            "fan_cooling_layer_time": 30,
            "enable_overhang_bridge_fan": True,
            "first_x_layer_fan_speed": 0,
            "pre_start_fan_time": 2,
            "overhang_threshold_participating_cooling": 95,
            "cooling_slowdown_logic": "uniform_cooling",
            "slow_down_min_speed": 10,
        },
        "warn": "PLA 冷却时序按官方默认：层时间超过 30s 才降速，首层不开风扇，悬垂 95% 触发全速。",
    })
    add({
        "id": "cooling-petg-slow",
        "when": {"filament": "PETG"},
        "set": {
            "fan_cooling_layer_time": 45,
            "enable_overhang_bridge_fan": True,
            "first_x_layer_fan_speed": 0,
            "pre_start_fan_time": 3,
            "overhang_threshold_participating_cooling": 90,
            "cooling_slowdown_logic": "uniform_cooling",
            "slow_down_min_speed": 15,
        },
        "warn": "PETG 层冷却时间放宽到 45s、悬垂风扇 90% 触发：过热会塌，过冷会翘边脱层。",
    })
    add({
        "id": "cooling-abs-asa",
        "when": {"filament": "ABS"},
        "set": {
            "fan_cooling_layer_time": 60,
            "enable_overhang_bridge_fan": False,
            "first_x_layer_fan_speed": 0,
            "pre_start_fan_time": 5,
            "cooling_slowdown_logic": "minimum_layer_time",
            "slow_down_min_speed": 20,
            "auxiliary_fan": False,
        },
        "warn": "ABS 关掉辅助风扇与悬垂风扇、层冷却放宽到 60s：一切冷风都会加剧翘边分层。",
    })
    add({
        "id": "cooling-asa",
        "when": {"filament": "ASA"},
        "set": {
            "fan_cooling_layer_time": 55,
            "enable_overhang_bridge_fan": False,
            "first_x_layer_fan_speed": 0,
            "pre_start_fan_time": 5,
            "cooling_slowdown_logic": "minimum_layer_time",
            "slow_down_min_speed": 18,
            "auxiliary_fan": False,
        },
        "warn": "ASA 同 ABS：关辅助风扇、放宽层冷却时间。",
    })

    # ---- 擦料塔：单色不需要、多色要够宽
    add({
        "id": "tower-single-color",
        "when": {"filament": "PLA"},
        "set": {
            "enable_prime_tower": True,
            "prime_tower_width": 35,
            "wipe_tower_bridging": 10,
            "prime_tower_rib_wall": True,
            "prime_tower_rib_width": 8,
            "prime_tower_infill_gap": 150,
            "prime_tower_skip_points": True,
            "prime_tower_lift_height": -1,
            "prime_tower_max_speed": 90,
            "wipe_tower_no_sparse_layers": False,
            "flush_into_infill": False,
            "flush_into_objects": False,
            "flush_into_support": True,
        },
        "warn": "擦料塔按单色保守配置：35 mm 宽、废料冲入支撑。多色工程建议在 Bambu Studio 里把宽度加到 60 mm。",
    })

    # ---- 回抽：按耗材与机型组合
    add({
        "id": "retract-direct-drive",
        "when": {"printer_group": "X1"},
        "set": {
            "retraction_length": 0.8,
            "retraction_speed": 30,
            "deretraction_speed": 30,
            "retract_before_wipe": 70,
            "retract_when_changing_layer": True,
            "wipe": True,
            "wipe_distance": 2,
            "retraction_minimum_travel": 2,
            "z_hop": 0.4,
            "z_hop_types": "Auto Lift",
            "reduce_infill_retraction_mode": "Auto",
            "use_firmware_retraction": False,
        },
        "warn": "X1 系列直驱短回抽：0.8 mm / 30 mm/s 是官方验证值，不要为了拉丝盲目加大。",
    })
    add({
        "id": "retract-bed-slinger",
        "when": {"printer_group": "A1"},
        "set": {
            "retraction_length": 0.8,
            "retraction_speed": 25,
            "deretraction_speed": 25,
            "retract_before_wipe": 60,
            "wipe": True,
            "wipe_distance": 2,
            "z_hop": 0.4,
            "z_hop_types": "Auto Lift",
        },
        "warn": "A1 系列床身运动：Z hop 用 Auto Lift 避免抬升刮蹭，回抽速度降一档减少齿轮打滑。",
    })

    # ---- Z 补偿：按耗材收缩特性
    add({
        "id": "z-comp-pla",
        "when": {"filament": "PLA"},
        "set": {"xy_hole_compensation": 0.02, "xy_contour_compensation": 0,
                "elefant_foot_compensation": 0.15,
                "elefant_foot_compensation_layers": 1},
        "warn": "PLA 收缩小：孔洞补 +0.02 mm 抵消收缩，象脚补偿 0.15 mm 压第一圈外翻。",
    })
    add({
        "id": "z-comp-petg",
        "when": {"filament": "PETG"},
        "set": {"xy_hole_compensation": 0.05, "xy_contour_compensation": 0,
                "elefant_foot_compensation": 0.2,
                "elefant_foot_compensation_layers": 2},
        "warn": "PETG 收缩与粘附都强：孔洞补到 +0.05 mm，象脚补偿 0.2 mm × 2 层（不然第一层会鼓边）。",
    })
    add({
        "id": "z-comp-abs-asa",
        "when": {"filament": "ABS"},
        "set": {"xy_hole_compensation": 0.1, "xy_contour_compensation": 0.02,
                "elefant_foot_compensation": 0.2,
                "elefant_foot_compensation_layers": 2},
        "warn": "ABS 收缩量最大（约 0.8%）：孔洞补 +0.1 mm、轮廓补 +0.02 mm，否则装不进去。",
    })
    add({
        "id": "z-comp-asa",
        "when": {"filament": "ASA"},
        "set": {"xy_hole_compensation": 0.09, "xy_contour_compensation": 0.02,
                "elefant_foot_compensation": 0.2,
                "elefant_foot_compensation_layers": 2},
        "warn": "ASA 收缩略小于 ABS：孔洞补 +0.09 mm，其余同 ABS。",
    })
    add({
        "id": "z-comp-tpu",
        "when": {"filament": "TPU"},
        "set": {"xy_hole_compensation": 0.04, "xy_contour_compensation": 0,
                "elefant_foot_compensation": 0.1,
                "elefant_foot_compensation_layers": 1},
        "warn": "TPU 弹性回缩：孔洞只补 +0.04 mm（补多了装配会松），象脚补偿降到 0.1 mm。",
    })

    # ---- 高度降速：高件用分段降速代替全局降速（省时间又抗振）
    add({
        "id": "height-slowdown-tall",
        "when": {"mode": "quality"},
        "set": {"enable_height_slowdown": 1,
                "slowdown_start_height": 120,
                "slowdown_end_height": 260,
                "slowdown_start_speed": 300,
                "slowdown_end_speed": 120,
                "slowdown_start_acc": 6000,
                "slowdown_end_acc": 2500},
        "warn": "开启高度分段降速：120 mm 以下正常速度，到 260 mm 降到 120 mm/s / 2500 mm/s²，"
                "专门对付高件上部的振纹，比全局降速省时间。",
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
