"""临时工具：打印一批关键键的归属 / preserve / soft 属性。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import schema, scope

KEYS = [
    "first_x_layer_fan_speed", "pre_start_fan_time", "slow_down_min_speed",
    "slow_down_layer_time", "fan_cooling_layer_time", "close_fan_the_first_x_layers",
    "full_fan_speed_layer", "additional_cooling_fan_speed", "enable_overhang_speed",
    "overhang_fan_speed", "overhang_fan_threshold", "reduce_fan_stop_start_freq",
    "slow_down_for_layer_cooling", "no_slow_down_for_cooling_on_outwalls",
    "activate_air_filtration", "during_print_exhaust_fan_speed",
    "complete_print_exhaust_fan_speed", "circle_compensation_speed",
    "ironing_fan_speed", "filament_flow_ratio", "filament_max_volumetric_speed",
    "pressure_advance", "enable_pressure_advance", "retraction_length",
    "retraction_speed", "deretraction_speed", "retraction_minimum_travel",
    "retract_before_wipe", "retract_restart_extra", "retract_when_changing_layer",
    "retract_lift_above", "retract_lift_below", "wipe", "wipe_distance",
    "z_hop", "z_hop_types", "support_air_filtration", "support_object_skip_flush",
    "enable_pre_heating", "auxiliary_fan", "max_layer_height", "min_layer_height",
    "prime_tower_width", "prime_tower_brim_width", "prime_tower_flat_ironing",
    "prime_tower_enable_framework", "prime_tower_lift_speed", "prime_tower_lift_height",
    "prime_tower_max_speed", "wipe_tower_rotation_angle", "wipe_tower_x", "wipe_tower_y",
    "wall_filament", "support_filament", "support_interface_filament",
    "initial_layer_flow_ratio", "print_flow_ratio", "prime_volume_mode",
    "flush_multiplier", "flush_multiplier_fast", "override_process_overhang_speed",
    "enable_arc_fitting", "seam_gap", "seam_slope_type", "seam_slope_start_height",
    "ironing_type", "ironing_flow", "ironing_spacing", "ironing_inset", "ironing_speed",
    "ironing_pattern", "ironing_direction", "support_interface_speed",
    "support_interface_pattern", "support_base_pattern", "support_base_pattern_spacing",
    "support_interface_loop_pattern", "support_interface_top_layers",
    "support_interface_bottom_layers", "support_expansion", "support_threshold_angle",
    "support_top_z_distance", "support_bottom_z_distance", "support_object_xy_distance",
    "support_on_build_plate_only", "support_type", "support_style",
    "tree_support_branch_angle", "tree_support_branch_diameter",
    "tree_support_branch_distance", "tree_support_wall_count",
    "spiral_mode", "wall_generator", "reduce_crossing_wall", "xy_hole_compensation",
    "xy_contour_compensation", "elefant_foot_compensation", "infill_wall_overlap",
    "top_bottom_infill_wall_overlap", "sparse_infill_pattern", "top_surface_pattern",
    "bottom_surface_pattern", "internal_solid_infill_pattern", "sub_top_surface_pattern",
    "smooth_coefficient", "fuzzy_skin", "resolution", "min_feature_size",
    "accel_to_decel_enable", "accel_to_decel_factor", "resonance_avoidance",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
    "gap_fill_speed", "bridge_acceleration", "internal_solid_infill_acceleration",
    "thick_bridges", "bridge_flow", "bridge_angle", "bridge_speed",
]

for k in KEYS:
    s = schema.spec(k)
    if s is None:
        print(f"{k:44s} <不在参数表>")
        continue
    print(f"{k:44s} scope={scope.scope_of(k):9s} preserve={s.preserve!s:5s} soft={s.soft!s:5s} kind={s.kind}")
