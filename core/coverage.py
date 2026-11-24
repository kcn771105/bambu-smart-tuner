"""参数覆盖说明：哪些键本程序会调，哪些不动，为什么不动。

这个模块是「确定所有能调的都有吗」这个问题的可核查答案：
所有分类都来自实测（tools/audit_coverage.py 对真实工程 + Bambu 官方预设的差集），
不是凭印象写的。
"""

from __future__ import annotations

EXCLUDED_CATEGORIES: list[tuple[str, str, tuple[str, ...], str]] = [
    (
        "硬件 / 机器定义",
        "由机型决定，改了就与真机不符，切片器也会用它做碰撞与限位检查",
        (
            "machine_max_speed_*", "machine_max_accel*", "machine_max_jerk_*",
            "machine_min_*", "machine_bed_mass_*", "machine_max_force_*",
            "machine_max_printed_mass", "machine_*_time", "machine_*_gcode",
            "nozzle_diameter", "nozzle_type", "nozzle_volume", "nozzle_height",
            "nozzle_volume_type", "required_nozzle_HRC", "diameter_limit",
            "printable_area", "printable_height", "bed_exclude_area",
            "bed_custom_model", "bed_custom_texture", "bed_heat_soak_area",
            "printer_model", "printer_variant", "printer_settings_id",
            "printer_structure", "printer_technology", "printer_extruder_*",
            "extruder_offset", "extruder_colour", "extruder_type",
            "extruder_variant_list", "extruder_printable_area",
            "extruder_printable_height", "extruder_clearance_*",
            "extruder_max_nozzle_count", "extruder_ams_count",
            "extruder_nozzle_stats*", "physical_extruder_map",
            "master_extruder_id", "print_extruder_id", "print_extruder_variant",
            "print_compatible_printers", "upward_compatible_machine",
            "default_nozzle_volume_type", "has_filament_switcher",
            "single_extruder_multi_material", "head_wrap_detect_zone",
            "grab_length", "silent_mode", "host_type", "printhost_*",
            "best_object_pos", "group_algo_with_time", "different_settings_to_system",
            "inherits_group", "use_relative_e_distances",
        ),
        "本程序通过 printers[].limits 读取机型的 max_speed / max_accel / 体积流量上限来"
        "钳制参数（只读不写），保证写出的值不会超过硬件能力。",
    ),
    (
        "温度 / 耗材身份",
        "属于耗材预设，跨材料、跨环境（室温、腔体、批次）差异极大，写死会直接废件",
        (
            "nozzle_temperature", "nozzle_temperature_initial_layer",
            "nozzle_temperature_range_*", "hot_plate_temp*", "cool_plate_temp*",
            "textured_plate_temp*", "eng_plate_temp*", "supertack_plate_temp*",
            "chamber_temperatures", "temperature_vitrification",
            "standby_temperature_delta", "hotend_heating_rate",
            "hotend_cooling_rate", "impact_strength_z",
            "filament_id", "filament_ids", "filament_type", "filament_vendor",
            "filament_colour", "filament_colour_type", "filament_cost",
            "filament_density", "filament_diameter", "filament_settings_id",
            "filament_is_*", "filament_notes", "filament_map", "filament_self_index",
            "filament_dev_*", "filament_extruder_*", "filament_multi_colour",
            "filament_mixed_*", "filament_volume_map", "filament_printable",
            "filament_soluble", "filament_metal_stickiness",
            "filament_scarf_*", "filament_ramming_*", "filament_prime_*",
            "filament_flush_*", "filament_change_length*",
            "filament_cooling_before_tower", "filament_tower_*",
            "filament_velocity_adaptation_factor", "filament_adaptive_volumetric_speed",
            "filament_enable_overhang_speed", "filament_overhang_*",
            "filament_bridge_speed", "filament_retract*", "filament_retraction_*",
            "filament_deretraction_speed", "filament_z_hop*", "filament_wipe*",
            "filament_shrink", "filament_adhesiveness_category",
            "filament_minimal_purge_on_wipe_tower", "filament_pre_*",
            "filament_preheat_temperature_delta", "curr_bed_type", "ams_*",
            "default_ams_type", "default_filament_colour", "default_filament_profile",
            "filament_start_gcode", "filament_end_gcode", "filament_long_retractions_when_ec",
            "filament_retraction_distances_when_ec",
        ),
        "温度与耗材身份整组不动。但耗材的可调特性（体积流量上限、风扇、流量比例、"
        "回抽、压力提前）会被读取——通过「同步 Bambu 自定义耗材」从你的预设里解析继承链拿到，"
        "用来覆盖内置基线。",
    ),
    (
        "多材料 / AMS 槽位",
        "记录「哪个对象用哪个 AMS 槽」，属于工程装配关系，改了会让换料逻辑错乱",
        (
            "flush_volumes_matrix", "flush_volumes_vector", "filament_map_mode",
            "filament_nozzle_map", "nozzle_flush_dataset", "sparse_infill_filament",
            "solid_infill_filament", "support_chamber_temp_control",
        ),
        "本程序只按第一种耗材、第一个喷嘴优化；擦料塔与 flush 的参数（宽度、抬升、"
        "废料冲入位置、倍率）是可调的，已在表内。",
    ),
    (
        "元数据 / G 代码",
        "不是工艺参数，改了会破坏工程结构或机器启动流程",
        (
            "name", "version", "from", "type", "setting_id", "inherits",
            "instantiation", "description", "compatible_printers*",
            "process_notes", "printer_notes", "print_settings_id",
            "default_print_profile", "filename_format", "thumbnail_size",
            "post_process", "gcode_flavor", "gcode_add_line_number",
            "before_layer_change_gcode", "layer_change_gcode",
            "change_filament_gcode", "time_lapse_gcode", "printing_by_object_gcode",
            "template_custom_gcode", "wrapping_detection_gcode",
            "wrapping_detection_layers", "wrapping_exclude_area",
            "enable_wrapping_detection", "scan_first_layer",
            "farthest_point_timelapse", "timelapse_type",
            "first_layer_print_sequence", "other_layers_print_sequence*",
            "fill_multiline", "periodic_modifier*", "exclude_object",
            "fan_direction", "curr_bed_type",
        ),
        "G 代码段与元数据一律原样保留，只在必要时清掉过期的切片产物"
        "（slice_info.config / *.gcode）。",
    ),
]

# 已覆盖、且会被规则主动改动的参数（65%）
COVERED_SUMMARY: list[tuple[str, str]] = [
    ("质量与线宽", "层高/首层层高、各特征线宽、墙层数与顶底壳层数、壳层最小厚度、切片精度（闭合半径/分辨率/最小特征）、圆弧拟合、磨砂皮肤、螺旋模式"),
    ("墙体高级", "墙生成器、墙打印顺序、过渡角度/长度/过滤偏差、薄壁检测、悬垂墙检测、垂直外壳、外墙精确走线、单墙首层、单调线延伸入墙、最小挤线宽度、交替加墙、互锁梁与分段互锁"),
    ("填充", "密度/图案/重叠/走线角度、顶底与次顶面图案与密度、顶面流量比、骨架与皮肤填充（密度/线宽/深度/图案）、晶格角度、共形填充全套、锚固、合并填充、旋转与偏移步进、最小填充面积"),
    ("速度", "外壁/内壁/稀疏与非稀疏填充/顶面/首层/首层填充/缝隙/小周长/垂直外壳/空走/Z 向空走/支撑/支撑接触面/桥接/悬垂 1-4/全悬垂、速度平滑系数、空走绕行距离、圆补偿速度"),
    ("加速度", "默认/外壁/内壁/稀疏填充/内部实心/顶面/首层/空走/桥接/首层空走/短距空走、减速系数与开关、高度分段降速（起止高度/速度/加速度）"),
    ("Jerk", "默认与外壁/内壁/填充/顶面/首层/空走，按机型分组（X1/P1/P2 = 9，A1 系 7~8）"),
    ("冷却", "风扇最小/最大、悬垂风扇与触发阈值、首 N 层不开风扇与全速层、辅助风扇开关与全速层、层冷却时间与降速逻辑、层时间平滑度、悬垂桥接风扇、提前开风扇时间、空气过滤与排风扇转速"),
    ("回抽", "回抽距离/速度、回填速度、擦嘴前回抽、重启动额外挤出、换层回抽、擦嘴与擦嘴距离、最小行程、Z hop 与方式、换料回抽、切断回抽、减少填充回抽模式、固件回抽开关"),
    ("擦料塔", "启用/宽度/过渡长度/旋转角/底座宽度、抬升高度与速度、最高速度、肋墙与肋宽、填充间隙、跳过尖角、不留稀疏层、废料冲入填充/对象/支撑、废料倍率、圆角墙、平面熨烫、位置 XY"),
    ("Z 轴与补偿", "Z 偏移、象脚补偿与补偿层数、XY 孔洞/轮廓补偿、圆补偿开关与偏移、精确 Z 高度、减少外墙穿越、收缩/孔洞补偿系数与限值"),
    ("接缝与斜切", "接缝位置/间隙、斜切类型/条件/整圈/间隙/最小长度/起始高度/层数/内壁、斜切角度阈值、避开悬垂、圆形斜接缝、擦嘴速度、走线起终点"),
    ("熨烫", "类型/图案/流量/间距/速度/内缩/方向/风扇"),
    ("悬垂与支撑", "启用/类型/样式/判定角/密度/主体图案与线距、顶底分离间隙与接触层数、接触面线距/图案/速度/环绕、XY 间距、首层间距、外扩、仅关键区域、仅落在热床、忽略小悬垂、独立层高、强制层数、支撑熨烫全套、树状支撑枝角/枝径/枝径角/枝距/墙数"),
    ("首层粘合", "裙边类型/宽度/与模型间距/圈数/高度/每件独立、筏板层数/接触距离/扩展/首层密度/首层扩展"),
    ("流量/压力提前/振纹", "流量比例、首层流量比例、全局流量比例、压力提前、自适应压力提前与悬垂自适应、摩擦补偿、共振规避与速度区间、体积流量系数、耗材体积流量上限"),
]

# 表内声明但默认不动，由用户按需手动开（界面会标出推荐值与何时该开）
ON_DEMAND: list[tuple[str, str, str]] = [
    ("磨砂皮肤 (fuzzy_skin_*)",
     "给表面加随机凹凸，做仿皮纹/织物手感",
     "默认 none。想用时在 Bambu Studio 里把「磨砂皮肤」设为 external，厚度 0.3 / 点距 0.8 已配好。"),
    ("螺旋花瓶模式 (spiral_mode*)",
     "连续上升打单壁，做花瓶/灯罩",
     "默认关闭。对实心件开启会得到空壳；只在单壁薄壳模型上手动开。"),
    ("筏板 (raft_*)",
     "整块底座，对付小接触面与翘边",
     "默认 0 层。小脚高件或严重翘边的料再开，参数已按 2 层筏板配好。"),
    ("支撑熨烫 (support_ironing_*, enable_support_ironing)",
     "把支撑接触面烫平，拆后不留痕",
     "默认关闭。外观件、接触面能看到时才值得开，会增加时间。"),
    ("共形填充 (conformal_*)",
     "沿曲面生成填充，适合薄壳曲面件",
     "默认关闭。只在曲面薄壳模型上有意义，普通件开了反而变慢。"),
    ("互锁梁 / 分段互锁 (interlocking_*, mmu_segmented_*)",
     "多材料界面的机械咬合，H2D 系列专用",
     "默认关闭。单色机与单材料件无意义，仅多材料混打时需要。"),
    ("AMS 槽位 (wall_filament, support_filament, support_interface_filament)",
     "指定某特征用哪个 AMS 槽",
     "保持 1。多色工程请直接在 Bambu Studio 里按对象分配，程序不代你决定配色。"),
    ("收缩系数曲线 (counter_coef_*, hole_coef_*, counter_limit_*, hole_limit_*)",
     "按外径分段补偿收缩，高阶标定用",
     "保持默认曲线。要精确补偿请用 Bambu Studio 的「尺寸补偿」向导实测，比盲调准。"),
    ("颜色渗透层 (top/bottom_color_penetration_layers)",
     "多色时让颜色渗入多少层，避免透底",
     "保持默认 5/3。单色件无意义；多色透底时再加大。"),
    ("G 代码段与元数据",
     "机器启动/结束/换料/延时摄影 G 代码，工程标识",
     "原样保留，一个字节都不动。"),
]


def coverage_report() -> str:
    """生成一份可直接贴进报告/界面的说明。"""
    from . import schema
    lines = [f"参数表共声明 {len(schema.PARAMS)} 个可调切片参数，分 {len(schema.GROUPS)} 组。", ""]
    lines.append("【已覆盖】")
    for name, desc in COVERED_SUMMARY:
        lines.append(f"  · {name}：{desc}")
    lines.append("")
    lines.append("【有意不改，且说明原因】")
    for name, why, keys, note in EXCLUDED_CATEGORIES:
        lines.append(f"  · {name}（{len(keys)} 类模式）")
        lines.append(f"      原因：{why}")
        lines.append(f"      做法：{note}")
    return "\n".join(lines)
