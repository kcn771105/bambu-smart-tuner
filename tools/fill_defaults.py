"""补齐规则库 defaults：为所有「非 soft」参数写一份 0.4 喷嘴 + 均衡取向的基准值。

值一律取自本机 Bambu Studio 官方预设解析后的真实默认（
resources/profiles/BBL + 真实工程 3mf），不是臆造。

已存在的不覆盖；只补缺的。输出到 rules/BambuRules.json 的 defaults 节点。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema   # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"

# 真实默认值（键名 = Bambu 键名，值 = 内存值，不是字符串）
DEFAULTS_2: dict = {
    # 熨烫（默认全关，开了才有意义）
    "ironing_type": "no ironing",
    "ironing_pattern": "zig-zag",
    "ironing_flow": 10,
    "ironing_spacing": 0.15,
    "ironing_speed": 30,
    "ironing_inset": 0.21,
    "ironing_direction": 45,
    "ironing_fan_speed": -1,

    # 接缝
    "seam_position": "aligned",
    "seam_gap": 15,
    "seam_placement_away_from_overhangs": False,
    "seam_slope_type": "none",
    "seam_slope_conditional": True,
    "seam_slope_entire_loop": False,
    "seam_slope_gap": 0,
    "seam_slope_min_length": 10,
    "seam_slope_start_height": 10,
    "seam_slope_steps": 10,
    "seam_slope_inner_walls": True,
    "scarf_angle_threshold": 155,
    "wipe_speed": 80,

    # 墙体高级
    "wall_generator": "classic",
    "wall_sequence": "inner wall/outer wall",
    "wall_distribution_count": 1,
    "wall_transition_angle": 10,
    "wall_transition_length": 100,
    "wall_transition_filter_deviation": 25,
    "only_one_wall_first_layer": False,
    "only_one_wall_top": False,
    "precise_outer_wall": False,
    "detect_thin_wall": False,
    "detect_overhang_wall": True,
    "ensure_vertical_shell_thickness": "enabled",
    "alternate_extra_wall": False,
    "monotonic_travel_into_wall": 45,
    "min_bead_width": 85,
    "top_one_wall_type": "all top",

    # 裙边 / 筏板
    "skirt_loops": 0,
    "skirt_height": 1,
    "skirt_distance": 2,
    "skirt_per_object": True,
    "raft_contact_distance": 0.1,
    "raft_expansion": 1.5,
    "raft_first_layer_density": 90,
    "raft_first_layer_expansion": -1,

    # 支撑补充
    "enable_support": False,
    "support_expansion": 0,
    "support_base_pattern_spacing": 2.5,
    "support_interface_spacing": 0.5,
    "support_interface_pattern": "auto",
    "support_interface_bottom_layers": 2,
    "support_interface_speed": 80,
    "support_object_first_layer_gap": 0.2,
    "support_critical_regions_only": False,
    "support_on_build_plate_only": False,
    "support_remove_small_overhang": True,
    "independent_support_layer_height": True,
    "enforce_support_layers": 0,
    "support_ironing_flow": 10,
    "support_ironing_spacing": 0.15,
    "support_ironing_speed": 30,
    "tree_support_branch_angle": 45,
    "tree_support_branch_diameter": 2,
    "tree_support_branch_diameter_angle": 5,
    "tree_support_branch_distance": 5,
    "tree_support_wall_count": -1,

    # 磨砂皮肤
    "fuzzy_skin": "none",
    "fuzzy_skin_thickness": 0.3,
    "fuzzy_skin_point_distance": 0.8,
    "fuzzy_skin_first_layer": False,
    "fuzzy_skin_mode": "displacement",
    "fuzzy_skin_noise_type": "classic",
    "fuzzy_skin_octaves": 4,
    "fuzzy_skin_persistence": 0.5,
    "fuzzy_skin_scale": 1,

    # 螺旋
    "spiral_mode": False,
    "spiral_mode_smooth": False,
    "spiral_mode_max_xy_smoothing": 200,

    # 桥接
    "bridge_angle": 0,
    "bridge_flow": 1,
    "bridge_no_support": False,
    "max_bridge_length": 0,
    "thick_bridges": False,
    "internal_bridge_support_thickness": 0.8,
    "counterbore_hole_bridging": "none",
    "overhang_totally_speed": 20,

    # 表面 / 壳层
    "top_surface_density": 100,
    "bottom_surface_density": 100,
    "bottom_surface_pattern": "monotonic",
    "sub_top_surface_pattern": "monotonic",
    "top_shell_thickness": 1,
    "bottom_shell_thickness": 0,
    "top_area_threshold": 200,
    "top_solid_infill_flow_ratio": 1.0,
    "top_color_penetration_layers": 5,
    "bottom_color_penetration_layers": 3,

    # 填充补充
    "infill_combination": False,
    "infill_rotate_step": 0,
    "infill_shift_step": 0.4,
    "infill_lock_depth": 1,
    "minimum_sparse_infill_area": 15,
    "infill_instead_top_bottom_surfaces": False,
    "sparse_infill_anchor": 400,
    "sparse_infill_anchor_max": 20,
    "symmetric_infill_y_axis": False,

    # 速度补充
    "gap_infill_speed": 250,
    "small_perimeter_speed": 50,
    "small_perimeter_threshold": 0,
    "vertical_shell_speed": 80,
    "travel_speed_z": 0,
    "slow_down_min_speed": 10,

    # 加速度补充
    "accel_to_decel_enable": False,
    "accel_to_decel_factor": 50,
    "initial_layer_travel_acceleration": 6000,
    "travel_short_distance_acceleration": 250,
    "enable_height_slowdown": 0,
    "slowdown_start_height": 0,
    "slowdown_end_height": 400,
    "slowdown_start_speed": 1000,
    "slowdown_end_speed": 1000,
    "slowdown_start_acc": 100000,
    "slowdown_end_acc": 100000,

    # 冷却补充
    "fan_cooling_layer_time": 30,
    "enable_overhang_bridge_fan": True,
    "first_x_layer_fan_speed": 0,
    "first_x_layer_part_fan_speed": 0,
    "pre_start_fan_time": 2,
    "close_additional_fan_first_x_layers": 3,
    "additional_fan_full_speed_layer": 0,
    "overhang_threshold_participating_cooling": 95,
    "slow_down_for_layer_cooling": True,
    "slow_down_layer_time": 12,
    "no_slow_down_for_cooling_on_outwalls": False,
    "cooling_slowdown_logic": "uniform_cooling",
    "reduce_fan_stop_start_freq": True,
    "auxiliary_fan": True,

    # 回抽补充
    "retract_length_toolchange": 2,
    "retract_restart_extra_toolchange": 0,
    "enable_long_retraction_when_cut": 2,
    "long_retractions_when_cut": 0,
    "reduce_infill_retraction_mode": "Auto",
    "use_firmware_retraction": False,

    # 擦料塔补充
    "prime_tower_lift_height": -1,
    "prime_tower_lift_speed": 90,
    "prime_tower_max_speed": 90,
    "prime_tower_rib_wall": True,
    "prime_tower_rib_width": 8,
    "prime_tower_infill_gap": 150,
    "prime_tower_skip_points": True,
    "wipe_tower_no_sparse_layers": False,
    "flush_into_infill": False,
    "flush_into_objects": False,
    "flush_into_support": True,
    "flush_multiplier": 1.0,

    # 其他工艺
    "precise_z_height": False,
    "slicing_mode": "regular",
    "slice_closing_radius": 0.049,
    "resolution": 0.012,
    "min_feature_size": 25,
    "enable_arc_fitting": True,
    "print_in_clockwise": False,
    "circle_compensation_manual_offset": 0,
    "enable_circle_compensation": False,
}

DEFAULTS_3: dict = {
    "min_layer_height": 0.08,
    "max_layer_height": 0.28,
    "initial_layer_infill_line_width": 0.5,
    "apply_scarf_seam_on_circles": True,
    "has_scarf_joint_seam": False,
    "override_filament_scarf_seam_setting": False,
    "role_base_wipe_speed": True,
    "embedding_wall_into_infill": False,
    "detect_floating_vertical_shell": True,
    "detect_narrow_internal_solid_infill": True,
    "filter_out_gap_fill": False,
    "interface_shells": False,
    "wall_filament": 1,
    "z_direction_outwall_speed_continuous": False,
    "smooth_coefficient": 4,
    "smooth_speed_discontinuity_area": True,
    "max_travel_detour_distance": 0,
    "circle_compensation_speed": 200,
    "override_process_overhang_speed": 0,
    "skeleton_infill_density": 15,
    "skeleton_infill_line_width": 0.45,
    "skin_infill_density": 15,
    "skin_infill_depth": 2,
    "skin_infill_line_width": 0.45,
    "sparse_infill_lattice_angle_1": -45,
    "sparse_infill_lattice_angle_2": 45,
    "locked_skeleton_infill_pattern": "zigzag",
    "locked_skin_infill_pattern": "crosszag",
    "is_infill_first": False,
    "modifier_ignore_infill": False,
    "support_angle": 0,
    "support_bottom_interface_spacing": 0.5,
    "support_interface_loop_pattern": False,
    "support_interface_not_for_body": True,
    "support_object_skip_flush": True,
    "support_cooling_filter": False,
    "support_fast_purge_mode": False,
    "enable_support_ironing": False,
    "support_ironing_direction": 0,
    "support_ironing_inset": 0,
    "support_ironing_pattern": "zig-zag",
    "support_filament": 1,
    "support_interface_filament": 1,
    "top_z_overrides_xy_distance": False,
    "prime_tower_enable_framework": False,
    "prime_tower_extra_rib_length": 0,
    "prime_tower_fillet_wall": True,
    "prime_tower_flat_ironing": True,
    "prime_volume_mode": "Default",
    "flush_multiplier_fast": 1.2,
    "enable_tower_interface_features": False,
    "wipe_tower_x": 15,
    "wipe_tower_y": 220,
    "cooling_filter_enabled": False,
    "cooling_perimeter_transition_distance": 10,
    "enable_pre_heating": False,
    "activate_air_filtration": False,
    "support_air_filtration": False,
    "during_print_exhaust_fan_speed": 70,
    "complete_print_exhaust_fan_speed": 70,
    "avoid_crossing_wall_includes_support": False,
    "draft_shield": "disabled",
    "enable_order_independent_overlap_carving": False,
    "ooze_prevention": False,
    "print_sequence": "by layer",
    "print_flow_ratio": 1.0,
    "conformal_infill": False,
    "conformal_pole": "layer",
    "conformal_ray_count": 0,
    "conformal_hub_radius": 0,
    "conformal_stagger": "none",
    "conformal_link_flip_layers": 0,
    "conformal_link_keep_layers": 1,
    "interlocking_beam": False,
    "interlocking_beam_width": 0.8,
    "interlocking_beam_layer_count": 2,
    "interlocking_depth": 2,
    "interlocking_orientation": 22.5,
    "interlocking_boundary_avoidance": 2,
}

# 第一批里声明了但 defaults 漏掉的软参数，一并补上
FILL_GAPS: dict = {
    "additional_cooling_fan_speed": 70,
    "retract_before_wipe": 70,
    "retract_restart_extra": 0,
    "wipe_distance": 2,
    "retract_lift_above": 0,
    "retract_lift_below": 0,
    "wipe_tower_rotation_angle": 0,
    "prime_tower_brim_width": 3,
    "elefant_foot_compensation_layers": 1,
    "xy_hole_compensation": 0,
    "xy_contour_compensation": 0,
    "support_bottom_z_distance": 0.2,
    "support_style": "default",
    "friction_compensation": 0,
    "min_resonance_avoidance_speed": 40,
    "max_resonance_avoidance_speed": 120,
    "raft_layers": 0,
}


DEFAULTS_4: dict = {
    "counter_coef_1": -0.0001,
    "counter_coef_2": 0.0,
    "counter_coef_3": 0.0,
    "counter_limit_max": 5.0,
    "counter_limit_min": -5.0,
    "hole_coef_1": 0.0001,
    "hole_coef_2": 0.0,
    "hole_coef_3": 0.0,
    "hole_limit_max": 5.0,
    "hole_limit_min": -5.0,
    "retraction_distances_when_cut": 2,
    "long_retractions_when_ec": 0,
    "retraction_distances_when_ec": 2,
    "mmu_segmented_region_interlocking_depth": 2,
    "mmu_segmented_region_max_width": 20,
    "start_end_points": "auto",
    "volumetric_speed_coefficients": 1.0,
    "filament_max_volumetric_speed": 21,
}


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8-sig"))
    defaults: dict = rules.setdefault("defaults", {})
    added, skipped = [], []

    for src in (DEFAULTS_2, DEFAULTS_3, DEFAULTS_4, FILL_GAPS):
        for k, v in src.items():
            if k not in schema.PARAMS:
                skipped.append(f"{k}（参数表里没有）")
                continue
            if k in defaults:
                continue
            defaults[k] = v
            added.append(k)

    # 还差哪些非 soft 参数没有基准值
    missing = [k for k, s in schema.PARAMS.items()
               if not s.soft and k not in defaults]
    # soft 参数也尽量给上，只是允许工程里没有
    missing_soft = [k for k, s in schema.PARAMS.items()
                    if s.soft and k not in defaults]

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"新增 {len(added)} 条基准值；defaults 现有 {len(defaults)} 条")
    if skipped:
        print(f"跳过 {len(skipped)} 条：")
        for s in skipped:
            print("   ", s)
    if missing:
        print(f"\n仍缺基准值的非 soft 参数（{len(missing)} 个）：")
        for k in missing:
            print("   ", k, "—", schema.PARAMS[k].label)
    if missing_soft:
        print(f"\n缺基准值的 soft 参数（{len(missing_soft)} 个，可接受）：{missing_soft}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
