"""参数表第三批：工艺细节与版本新特性。

这三批加起来覆盖 Bambu Studio 工程里**所有可调切片参数**；
剩下未声明的键分三类，属于结构上不该由调参工具改的：

  · 硬件/机器定义：machine_max_*、nozzle_diameter、printable_area、extruder_*
  · 温度与耗材身份：nozzle_temperature、hot_plate_temp、filament_id、filament_colour
  · 元数据/G 代码/多材料槽位：name、version、*_gcode、flush_volumes_*、print_extruder_id

它们在 UI 的「未覆盖参数」页会明确列出来并说明原因，不静默忽略。
"""

EXTRA_PARAMS_3: list[tuple] = [
    # ============================================================ 层高范围（自动层高用）
    ("min_layer_height", "最小层高", "quality", "array_float", 0.02, 0.3, 0.01, "mm", (), 2, True),
    ("max_layer_height", "最大层高", "quality", "array_float", 0.05, 0.8, 0.01, "mm", (), 2, True),
    ("initial_layer_infill_line_width", "首层填充线宽", "quality", "float", 0.1, 2.0, 0.01, "mm", (), 2, True),

    # ============================================================ 接缝 / 表面补充
    ("apply_scarf_seam_on_circles", "圆形也做斜接缝", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("has_scarf_joint_seam", "已有斜接缝", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("override_filament_scarf_seam_setting", "覆盖耗材斜接缝设置", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("role_base_wipe_speed", "按角色擦嘴速度", "seam", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 墙 / 壳层补充
    ("embedding_wall_into_infill", "墙嵌入填充", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("detect_floating_vertical_shell", "检测悬空垂直壳", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("detect_narrow_internal_solid_infill", "检测窄内部实心", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("filter_out_gap_fill", "滤除缝隙填充", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("interface_shells", "接触面外壳", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("wall_filament", "墙使用耗材槽（0=不指定）", "wall", "int", 0, 16, 1, "", (), 0, True, True),

    # ============================================================ 速度补充
    ("z_direction_outwall_speed_continuous", "Z 向外壁速度连续", "speed", "bool", 0, 1, 1, "", (), 0, True),
    ("smooth_coefficient", "速度平滑系数", "speed", "int", 1, 150, 1, "", (), 0, True, True),
    ("smooth_speed_discontinuity_area", "平滑速度突变区", "speed", "bool", 0, 1, 1, "", (), 0, True),
    ("max_travel_detour_distance", "空走绕行最大距离", "speed", "float", 0, 500, 5, "mm", (), 0, True),
    ("circle_compensation_speed", "圆补偿速度", "speed", "array_float", 10, 500, 10, "mm/s", (), 0, True),
    ("override_process_overhang_speed", "覆盖工艺悬垂速度", "speed", "array_float", 0, 1, 1, "", (), 0, True),

    # ============================================================ 填充补充（骨架 / 皮肤 / 晶格）
    ("skeleton_infill_density", "骨架填充密度", "infill", "pct", 0, 100, 5, "%", (), 0, True),
    ("skeleton_infill_line_width", "骨架填充线宽", "infill", "float", 0.1, 2, 0.01, "mm", (), 2, True),
    ("skin_infill_density", "皮肤填充密度", "infill", "pct", 0, 100, 5, "%", (), 0, True),
    ("skin_infill_depth", "皮肤填充深度", "infill", "int", 0, 20, 1, "层", (), 0, True),
    ("skin_infill_line_width", "皮肤填充线宽", "infill", "float", 0.1, 2, 0.01, "mm", (), 2, True),
    ("sparse_infill_lattice_angle_1", "晶格填充角 1", "infill", "float", -90, 90, 5, "°", (), 0, True),
    ("sparse_infill_lattice_angle_2", "晶格填充角 2", "infill", "float", -90, 90, 5, "°", (), 0, True),
    ("locked_skeleton_infill_pattern", "骨架填充图案", "infill", "enum", 0, 0, 1, "",
     ("zigzag", "crosszag", "grid", "triangles"), 2, True),
    ("locked_skin_infill_pattern", "皮肤填充图案", "infill", "enum", 0, 0, 1, "",
     ("crosszag", "zigzag", "grid", "triangles"), 2, True),
    ("is_infill_first", "先打填充", "infill", "bool", 0, 1, 1, "", (), 0, True),
    ("modifier_ignore_infill", "修改器忽略填充", "infill", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 支撑补充
    ("support_angle", "支撑角度（旧版）", "support", "float", 0, 90, 1, "°", (), 0, True),
    ("support_bottom_interface_spacing", "支撑底面接触线距", "support", "float", 0, 5, 0.05, "mm", (), 2, True),
    ("support_interface_loop_pattern", "接触面环绕图案", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_interface_not_for_body", "接触面不用于主体", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_object_skip_flush", "支撑跳过冲洗", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_cooling_filter", "支撑冷却过滤", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_fast_purge_mode", "支撑快速冲洗模式", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("enable_support_ironing", "启用支撑熨烫", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_ironing_direction", "支撑熨烫方向", "support", "float", 0, 360, 5, "°", (), 0, True),
    ("support_ironing_inset", "支撑熨烫内缩", "support", "float", 0, 2, 0.01, "mm", (), 2, True),
    ("support_ironing_pattern", "支撑熨烫图案", "support", "enum", 0, 0, 1, "",
     ("zig-zag", "concentric", "rectilinear"), 2, True),
    ("support_filament", "支撑使用耗材槽（0=不指定）", "support", "int", 0, 16, 1, "", (), 0, True, True),
    ("support_interface_filament", "支撑接触面耗材槽（0=不指定）", "support", "int", 0, 16, 1, "", (), 0, True, True),
    ("top_z_overrides_xy_distance", "顶面间隙覆盖 XY 间距", "support", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 擦料塔补充
    ("prime_tower_enable_framework", "擦料塔启用框架", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("prime_tower_extra_rib_length", "擦料塔额外肋长", "tower", "float", 0, 50, 1, "mm", (), 0, True),
    ("prime_tower_fillet_wall", "擦料塔圆角墙", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("prime_tower_flat_ironing", "擦料塔平面熨烫", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("prime_volume_mode", "擦料体积模式", "tower", "enum", 0, 0, 1, "",
     ("Default", "Custom", "None"), 2, True),
    ("flush_multiplier_fast", "快速废料倍率", "tower", "array_float", 0, 3, 0.05, "×", (), 2, True),
    ("enable_tower_interface_features", "擦料塔接触面特性", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("wipe_tower_x", "擦料塔 X 位置", "tower", "float", 0, 500, 1, "mm", (), 1, True, True),
    ("wipe_tower_y", "擦料塔 Y 位置", "tower", "float", 0, 500, 1, "mm", (), 1, True, True),

    # ============================================================ 冷却 / 环境
    ("cooling_filter_enabled", "启用冷却过滤", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("cooling_perimeter_transition_distance", "周长冷却过渡距离", "cooling", "array_float", 0, 100, 1, "mm", (), 0, True),
    ("enable_pre_heating", "启用预热", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("activate_air_filtration", "启用空气过滤", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("support_air_filtration", "支撑打印时过滤", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("during_print_exhaust_fan_speed", "打印中排风扇转速", "cooling", "pct_num", 0, 100, 5, "%", (), 0, True),
    ("complete_print_exhaust_fan_speed", "打印后排风扇转速", "cooling", "pct_num", 0, 100, 5, "%", (), 0, True),

    # ============================================================ 其他工艺开关
    ("avoid_crossing_wall_includes_support", "避墙时也避支撑", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("draft_shield", "挡风罩", "quality", "enum", 0, 0, 1, "",
     ("disabled", "enabled", "auto"), 2, True),
    ("enable_order_independent_overlap_carving", "顺序无关重叠切割", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("ooze_prevention", "防渗料", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("print_sequence", "打印顺序", "quality", "enum", 0, 0, 1, "",
     ("by layer", "by object"), 2, False),
    ("print_flow_ratio", "全局流量比例", "flow", "float", 0.5, 1.5, 0.01, "", (), 3, True),

    # ============================================================ 一致性 / 交叉填充（Conformal）
    ("conformal_infill", "共形填充", "infill", "bool", 0, 1, 1, "", (), 0, True),
    ("conformal_pole", "共形填充极点", "infill", "enum", 0, 0, 1, "",
     ("layer", "none"), 2, True),
    ("conformal_ray_count", "共形射线数", "infill", "int", 0, 64, 1, "", (), 0, True),
    ("conformal_hub_radius", "共形轮毂半径", "infill", "float", 0, 50, 1, "mm", (), 1, True),
    ("conformal_stagger", "共形错位", "infill", "enum", 0, 0, 1, "",
     ("none", "stagger"), 2, True),
    ("conformal_link_flip_layers", "共形连接翻转层", "infill", "int", 0, 20, 1, "", (), 0, True),
    ("conformal_link_keep_layers", "共形连接保持层", "infill", "int", 0, 20, 1, "", (), 0, True),

    # ============================================================ 互锁（H2D 等多材料）
    ("interlocking_beam", "互锁梁", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("interlocking_beam_width", "互锁梁宽度", "wall", "float", 0.2, 5, 0.1, "mm", (), 1, True),
    ("interlocking_beam_layer_count", "互锁梁层数", "wall", "int", 1, 20, 1, "层", (), 0, True),
    ("interlocking_depth", "互锁深度", "wall", "int", 0, 20, 1, "层", (), 0, True),
    ("interlocking_orientation", "互锁取向", "wall", "float", 0, 360, 2.5, "°", (), 1, True),
    ("interlocking_boundary_avoidance", "互锁边界避让", "wall", "int", 0, 20, 1, "层", (), 0, True),
]
