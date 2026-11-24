"""推导「切片工艺 / 耗材页 / 机器页」参数归属，生成 core/scope_data.py

依据（全部来自 Bambu Studio 自带的官方预设，不是拍脑袋）：

    C:\\Program Files\\Bambu Studio\\resources\\profiles\\BBL\\
        machine\\    ← 机器页预设（机型）
        filament\\   ← 耗材页预设（耗材）
        process\\    ← 切片工艺预设（过程）

Bambu Studio 把这三个目录分别挂在「机器 / 耗材 / 质量(工艺)」三个页面上，
所以「某个键出现在哪个目录」就等价于「这个键属于哪一页」。

本脚本做两件事：

    1. 扫官方预设目录，得到 PROCESS_KEYS / FILAMENT_KEYS / MACHINE_KEYS 三个集合；
    2. 对官方预设里没出现的新版键（fuzzy_skin / conformal_infill / jerk 等），
       用一张人工表 MANUAL 判定归属。

产物：core/scope_data.py（纯静态表，程序运行时不再依赖本机装了 Bambu Studio）。

用法：
    python tools/derive_scope.py            # 只打印统计
    python tools/derive_scope.py --apply    # 写出 core/scope_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema  # noqa: E402

PRESET_ROOT = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")

# ---------------------------------------------------------------- 人工判定表
# 官方三个预设目录里都查不到的键（新版本特性 / Orca 移植键 / 已被官方删掉的键）。
# 值含义：
#   process = 切片工艺页（默认允许写入）
#   filament = 耗材页（默认只读）
#   machine  = 机器页（默认只读）
MANUAL: dict[str, str] = {
    # ---- 磨砂皮肤 / 螺旋 / 共形填充 / 互锁梁：都是切片工艺页的新特性
    "fuzzy_skin": "process", "fuzzy_skin_thickness": "process",
    "fuzzy_skin_point_distance": "process", "fuzzy_skin_first_layer": "process",
    "fuzzy_skin_mode": "process", "fuzzy_skin_noise_type": "process",
    "fuzzy_skin_octaves": "process", "fuzzy_skin_persistence": "process",
    "fuzzy_skin_scale": "process",
    "spiral_mode": "process", "spiral_mode_smooth": "process",
    "spiral_mode_max_xy_smoothing": "process",
    "conformal_infill": "process", "conformal_pole": "process",
    "conformal_ray_count": "process", "conformal_hub_radius": "process",
    "conformal_stagger": "process", "conformal_link_flip_layers": "process",
    "conformal_link_keep_layers": "process",
    "interlocking_beam": "process", "interlocking_beam_width": "process",
    "interlocking_beam_layer_count": "process", "interlocking_depth": "process",
    "interlocking_orientation": "process",
    "interlocking_boundary_avoidance": "process",
    "mmu_segmented_region_interlocking_depth": "process",
    "mmu_segmented_region_max_width": "process",

    # ---- 工艺页的顶底面 / 填充细节
    "top_surface_density": "process", "bottom_surface_density": "process",
    "sub_top_surface_pattern": "process", "top_area_threshold": "process",
    "top_solid_infill_flow_ratio": "process",
    "top_color_penetration_layers": "process",
    "bottom_color_penetration_layers": "process",
    "top_bottom_infill_wall_overlap": "process",
    "internal_solid_infill_pattern": "process",
    "sparse_infill_anchor": "process", "sparse_infill_anchor_max": "process",
    "symmetric_infill_y_axis": "process", "is_infill_first": "process",
    "modifier_ignore_infill": "process",
    "infill_instead_top_bottom_surfaces": "process",
    "sparse_infill_lattice_angle_1": "process",
    "sparse_infill_lattice_angle_2": "process",
    "minimum_sparse_infill_area": "process",
    "infill_lock_depth": "process", "infill_rotate_step": "process",
    "infill_shift_step": "process",

    # ---- 墙体高级
    "wall_sequence": "process", "wall_distribution_count": "process",
    "wall_transition_angle": "process", "wall_transition_length": "process",
    "wall_transition_filter_deviation": "process",
    "only_one_wall_first_layer": "process", "only_one_wall_top": "process",
    "precise_outer_wall": "process", "detect_thin_wall": "process",
    "detect_overhang_wall": "process",
    "ensure_vertical_shell_thickness": "process",
    "alternate_extra_wall": "process",
    "monotonic_travel_into_wall": "process", "min_bead_width": "process",
    "top_one_wall_type": "process", "embedding_wall_into_infill": "process",
    "detect_floating_vertical_shell": "process",
    "detect_narrow_internal_solid_infill": "process",
    "filter_out_gap_fill": "process", "interface_shells": "process",
    "wall_filament": "filament",          # AMS 槽位，属于耗材身份
    "support_filament": "filament",       # AMS 槽位（官方目录在 process，但语义是耗材身份）
    "support_interface_filament": "filament",
    "print_extruder_variant": "machine",  # 热端类型（官方目录在 process，但语义是机器）
    "print_extruder_id": "machine",
    "print_settings_id": "meta",
    "compatible_printers": "meta",

    # ---- 熨烫 / 接缝
    "ironing_pattern": "process", "ironing_direction": "process",
    "ironing_fan_speed": "filament",      # 风扇转速属耗材页
    "enable_support_ironing": "process",
    "support_ironing_direction": "process", "support_ironing_flow": "process",
    "support_ironing_inset": "process", "support_ironing_pattern": "process",
    "support_ironing_spacing": "process", "support_ironing_speed": "process",
    "seam_gap": "process", "seam_slope_conditional": "process",
    "seam_slope_entire_loop": "process", "seam_slope_inner_walls": "process",
    "seam_slope_steps": "process",
    "apply_scarf_seam_on_circles": "process",
    "has_scarf_joint_seam": "process",
    "start_end_points": "process",
    "wipe_speed": "process", "role_base_wipe_speed": "process",

    # ---- 支撑补充
    "support_angle": "process",
    "support_bottom_interface_spacing": "process",
    "support_critical_regions_only": "process",
    "support_remove_small_overhang": "process",
    "independent_support_layer_height": "process",
    "enforce_support_layers": "process",
    "support_interface_not_for_body": "process",
    "support_cooling_filter": "process",
    "support_fast_purge_mode": "process",
    "support_object_first_layer_gap": "process",
    "top_z_overrides_xy_distance": "process",
    "support_density": "process",         # 官方已删除该键（疏密由 spacing 表达）

    # ---- 擦料塔的补充特性（塔本体属工艺页）
    "prime_tower_rib_wall": "process", "prime_tower_rib_width": "process",
    "prime_tower_infill_gap": "process", "prime_tower_skip_points": "process",
    "prime_tower_fillet_wall": "process",
    "prime_tower_extra_rib_length": "process",
    "flush_into_infill": "process", "flush_into_objects": "process",
    "flush_into_support": "process",
    "enable_tower_interface_features": "process",

    # ---- 冷却相关（官方放在耗材页）
    "first_x_layer_part_fan_speed": "filament",
    "close_additional_fan_first_x_layers": "filament",
    "additional_fan_full_speed_layer": "filament",
    "enable_overhang_bridge_fan": "filament",
    "overhang_threshold_participating_cooling": "filament",
    "cooling_filter_enabled": "filament",
    "cooling_perimeter_transition_distance": "filament",
    "cooling_slowdown_logic": "filament",

    # ---- 流量 / 压力提前 / 振纹（Bambu 把「流量」放在耗材页）
    "pressure_advance": "filament", "enable_pressure_advance": "filament",
    "adaptive_pressure_advance": "filament",
    "adaptive_pressure_advance_overhangs": "filament",
    "friction_compensation": "filament",
    "resonance_avoidance": "filament",
    "min_resonance_avoidance_speed": "filament",
    "max_resonance_avoidance_speed": "filament",
    "initial_layer_flow_ratio": "filament",
    "print_flow_ratio": "filament",

    # ---- 回抽补充（机器页）
    "use_firmware_retraction": "machine",
    "reduce_infill_retraction_mode": "machine",
    "retraction_distances_when_ec": "machine",
    "long_retractions_when_ec": "machine",

    # ---- Jerk / 加减速（机器页；官方只有 machine_max_jerk_*）
    "default_jerk": "machine", "outer_wall_jerk": "machine",
    "inner_wall_jerk": "machine", "infill_jerk": "machine",
    "top_surface_jerk": "machine", "initial_layer_jerk": "machine",
    "travel_jerk": "machine",
    "accel_to_decel_enable": "process", "accel_to_decel_factor": "process",
    "travel_short_distance_acceleration": "process",

    # ---- Z 偏移（机器校准项）
    "z_offset": "machine",

    # ---- 擦料塔盘面摆位
    "wipe_tower_x": "machine", "wipe_tower_y": "machine",
    "wipe_tower_bridging": "machine", "wipe_tower_rotation_angle": "machine",

    # ---- 其它工艺页
    "draft_shield": "process", "ozone_prevention": "process",
    "min_feature_size": "process", "slice_closing_radius": "process",
    "slicing_mode": "process", "print_in_clockwise": "process",
    "raft_contact_distance": "process", "raft_expansion": "process",
    "raft_first_layer_density": "process",
    "raft_first_layer_expansion": "process",
    "skirt_per_object": "process", "brim_type": "process",
    "gap_fill_speed": "process",
    "internal_solid_infill_acceleration": "process",
    "bridge_acceleration": "process",
    "bridge_angle": "process", "counterbore_hole_bridging": "process",
    "elefant_foot_compensation_layers": "process",
    "min_resonance_avoidance_speed": "filament",
    "prime_volume_mode": "filament",
    "flush_multiplier": "filament", "flush_multiplier_fast": "filament",
}


def preset_keys(sub: str) -> set[str]:
    """某个官方预设目录里出现过的所有键。"""
    out: set[str] = set()
    d = PRESET_ROOT / sub
    if not d.exists():
        return out
    for f in d.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(j, dict):
            out |= {str(k) for k in j.keys()}
    return out


def build() -> dict[str, str]:
    """返回 {键: scope}，scope ∈ {process, filament, machine}。"""
    fil = preset_keys("filament")
    mach = preset_keys("machine")
    proc = preset_keys("process")

    scope: dict[str, str] = {}
    for key in schema.PARAMS:
        if key in MANUAL:
            scope[key] = MANUAL[key]
        elif key in proc:
            scope[key] = "process"
        elif key in fil:
            scope[key] = "filament"
        elif key in mach:
            scope[key] = "machine"
        elif key.startswith("machine_"):
            scope[key] = "machine"
        elif key.startswith("filament_"):
            scope[key] = "filament"
        else:
            # 兜底：按 schema 分组猜
            g = schema.PARAMS[key].group
            if g in ("cooling", "flow"):
                scope[key] = "filament"
            elif g in ("retraction", "tower"):
                scope[key] = "filament"
            else:
                scope[key] = "process"
    return scope


HEADER = '''"""参数归属表（自动生成，勿手改）

生成命令：python tools/derive_scope.py --apply

Bambu Studio 把官方预设分成三个目录，正好对应它的三个页面：

    profiles/BBL/process/    切片工艺页（质量/强度/速度/其他）
    profiles/BBL/filament/   耗材页
    profiles/BBL/machine/    机器页

所以「键出现在哪个目录」就等价于「这个键属于哪一页」。
本程序默认只写 process（工艺页），filament / machine 一律只读不改。

每个值还有一条简短说明，UI 上展示「为什么不改」。
"""

# scope → (中文页名, 说明)
SCOPE_LABEL: dict[str, str] = {
    "process": "切片工艺",
    "filament": "耗材页",
    "machine": "机器页",
    "meta": "工程元数据",
}

SCOPE_NOTE: dict[str, str] = {
    "process": "属于切片工艺参数，本程序可写。",
    "filament": "属于耗材页参数（冷却/回抽/流量/AMS 槽位），按要求不改。",
    "machine": "属于机器页参数（硬件上限/喷嘴/板面/起始 G-code），按要求不改。",
    "meta": "工程身份信息（机型/耗材标识/继承关系），不可改。",
}

# 键 → scope
SCOPE: dict[str, str] = {
'''

FOOTER = "}\n"


def main() -> int:
    scope = build()
    buckets: dict[str, list[str]] = {"process": [], "filament": [], "machine": []}
    for k, v in scope.items():
        buckets[v].append(k)

    print("参数归属统计（来自官方预设目录）")
    for name in ("process", "filament", "machine"):
        print(f"  {name:9s} {len(buckets[name]):4d}")
    print(f"  合计      {len(scope):4d}")
    manual_only = [k for k in scope if k in MANUAL]
    print(f"其中人工判定 {len(manual_only)} 个（官方目录查不到的新键）")

    if "--apply" in sys.argv:
        lines = [HEADER]
        for k in sorted(scope):
            lines.append(f'    "{k}": "{scope[k]}",\n')
        lines.append(FOOTER)
        out = ROOT / "core" / "scope_data.py"
        out.write_text("".join(lines), encoding="utf-8")
        print(f"\n已写出 {out}（{out.stat().st_size} bytes）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
