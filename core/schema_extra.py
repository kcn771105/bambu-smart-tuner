"""参数表第二批：补齐 Bambu Studio 工程里真实存在、但第一批没覆盖的切片参数。

来源：本机 Bambu Studio 官方预设（resources/profiles/BBL）与真实工程 3mf 的
`Metadata/project_settings.config`，键名、取值形态（"50%" / ["80","80"] / "monotonic"）
与合法区间都按实测填写，不是推测。

这里只用「元组」描述，由 schema.py 转成 ParamSpec，避免循环导入。

元组字段：
    (key, label, group, kind, vmin, vmax, step, unit, choices, decimals, soft)

kind 取值见 schema.py：float / int / pct / pct_num / array_float / array_pct /
                        array_str / enum / bool / enum_array
"""

EXTRA_PARAMS: list[tuple] = [
    # ============================================================ 熨烫
    ("ironing_type", "熨烫类型", "ironing", "enum", 0, 0, 1, "",
     ("no ironing", "top", "topmost", "solid"), 2, False),
    ("ironing_pattern", "熨烫图案", "ironing", "enum", 0, 0, 1, "",
     ("zig-zag", "concentric", "rectilinear", "monotonic", "monotonicline"), 2, False),
    ("ironing_flow", "熨烫流量", "ironing", "pct", 1, 60, 1, "%", (), 0, False),
    ("ironing_spacing", "熨烫走线间距", "ironing", "float", 0.05, 1.0, 0.01, "mm", (), 2, False),
    ("ironing_speed", "熨烫速度", "ironing", "float", 5, 200, 5, "mm/s", (), 0, False),
    ("ironing_inset", "熨烫内缩", "ironing", "float", 0, 2, 0.01, "mm", (), 2, False),
    ("ironing_direction", "熨烫方向", "ironing", "float", 0, 360, 5, "°", (), 0, False),
    ("ironing_fan_speed", "熨烫风扇", "ironing", "array_float", -1, 100, 5, "%", (), 0, True),

    # ============================================================ 接缝 / 接缝斜切
    ("seam_position", "接缝位置", "seam", "enum", 0, 0, 1, "",
     ("nearest", "aligned", "back", "random", "aligned_back"), 2, False),
    ("seam_gap", "接缝间隙", "seam", "pct", 0, 50, 1, "%", (), 0, False),
    ("seam_placement_away_from_overhangs", "接缝避开悬垂", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("seam_slope_type", "接缝斜切类型", "seam", "enum", 0, 0, 1, "",
     ("none", "external", "all", "hidden"), 2, False),
    ("seam_slope_conditional", "斜切仅用于外露", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("seam_slope_entire_loop", "斜切覆盖整圈", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("seam_slope_gap", "斜切间隙", "seam", "float", 0, 5, 0.1, "mm", (), 1, True),
    ("seam_slope_min_length", "斜切最小长度", "seam", "float", 0, 100, 1, "mm", (), 0, True),
    ("seam_slope_start_height", "斜切起始高度", "seam", "pct", 0, 100, 5, "%", (), 0, True),
    ("seam_slope_steps", "斜切层数", "seam", "int", 1, 50, 1, "层", (), 0, True),
    ("seam_slope_inner_walls", "内壁也做斜切", "seam", "bool", 0, 1, 1, "", (), 0, True),
    ("scarf_angle_threshold", "斜切角度阈值", "seam", "float", 0, 180, 5, "°", (), 0, True),
    ("wipe_speed", "擦嘴速度", "seam", "pct", 0, 200, 5, "%", (), 0, True),

    # ============================================================ 墙体高级
    ("wall_generator", "墙生成器", "wall", "enum", 0, 0, 1, "",
     ("classic", "arachne"), 2, False, True),
    ("wall_sequence", "墙打印顺序", "wall", "enum", 0, 0, 1, "",
     ("inner wall/outer wall", "outer wall/inner wall", "inner-outer-inner wall"), 2, False),
    ("wall_distribution_count", "墙均匀分配数", "wall", "int", 1, 4, 1, "", (), 0, True),
    ("wall_transition_angle", "墙过渡角度", "wall", "float", 0, 90, 1, "°", (), 0, True),
    ("wall_transition_length", "墙过渡长度", "wall", "pct", 0, 500, 5, "%", (), 0, True),
    ("wall_transition_filter_deviation", "墙过渡过滤偏差", "wall", "pct", 0, 100, 1, "%", (), 0, True),
    ("only_one_wall_first_layer", "首层只打一圈墙", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("only_one_wall_top", "顶面只打一圈墙", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("precise_outer_wall", "外壁精确走线", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("detect_thin_wall", "检测薄壁", "wall", "bool", 0, 1, 1, "", (), 0, False),
    ("detect_overhang_wall", "检测悬垂墙", "wall", "bool", 0, 1, 1, "", (), 0, False),
    ("ensure_vertical_shell_thickness", "保证垂直外壳厚度", "wall", "enum", 0, 0, 1, "",
     ("enabled", "disabled", "partial"), 2, True),
    ("alternate_extra_wall", "交替加墙", "wall", "bool", 0, 1, 1, "", (), 0, True),
    ("monotonic_travel_into_wall", "单调线延伸入墙比例", "wall", "pct", 0, 200, 5, "%", (), 0, True),
    ("min_bead_width", "最小挤线宽度", "wall", "pct", 10, 200, 5, "%", (), 0, True),
    ("top_one_wall_type", "顶面单墙类型", "wall", "enum", 0, 0, 1, "",
     ("all top", "top and bottom", "top only"), 2, True),

    # ============================================================ 裙边 / 筏板
    ("skirt_loops", "裙边圈数", "adhesion", "int", 0, 10, 1, "圈", (), 0, False),
    ("skirt_height", "裙边层数", "adhesion", "int", 1, 10, 1, "层", (), 0, False),
    ("skirt_distance", "裙边距离", "adhesion", "float", 0, 30, 1, "mm", (), 0, False),
    ("skirt_per_object", "每个对象单独裙边", "adhesion", "bool", 0, 1, 1, "", (), 0, True),
    ("raft_contact_distance", "筏板接触间距", "adhesion", "float", 0, 1, 0.01, "mm", (), 2, True),
    ("raft_expansion", "筏板扩展", "adhesion", "float", 0, 10, 0.5, "mm", (), 1, True),
    ("raft_first_layer_density", "筏板首层密度", "adhesion", "pct", 10, 100, 5, "%", (), 0, True),
    ("raft_first_layer_expansion", "筏板首层扩展", "adhesion", "float", -5, 10, 0.5, "mm", (), 1, True),

    # ============================================================ 支撑（补充）
    ("enable_support", "启用支撑", "support", "bool", 0, 1, 1, "", (), 0, False),
    ("support_expansion", "支撑外扩", "support", "float", -1, 5, 0.05, "mm", (), 2, True),
    ("support_base_pattern_spacing", "支撑主体线距", "support", "float", 0.5, 10, 0.1, "mm", (), 2, False),
    ("support_interface_spacing", "支撑接触面线距", "support", "float", 0, 5, 0.05, "mm", (), 2, False),
    ("support_interface_pattern", "支撑接触面图案", "support", "enum", 0, 0, 1, "",
     ("auto", "grid", "rectilinear", "concentric"), 2, False),
    ("support_interface_bottom_layers", "支撑底面接触层数", "support", "int", 0, 10, 1, "层", (), 0, True),
    ("support_interface_speed", "支撑接触面速度", "support", "array_float", 5, 1000, 5, "mm/s", (), 0, True),
    ("support_object_first_layer_gap", "支撑首层间距", "support", "float", 0, 2, 0.05, "mm", (), 2, True),
    ("support_critical_regions_only", "仅关键区域加支撑", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_on_build_plate_only", "支撑仅落在热床", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("support_remove_small_overhang", "忽略小悬垂", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("independent_support_layer_height", "支撑独立层高", "support", "bool", 0, 1, 1, "", (), 0, True),
    ("enforce_support_layers", "强制支撑层数", "support", "int", 0, 20, 1, "层", (), 0, True),
    ("support_ironing_flow", "支撑熨烫流量", "support", "pct", 1, 60, 1, "%", (), 0, True),
    ("support_ironing_spacing", "支撑熨烫间距", "support", "float", 0.05, 1, 0.01, "mm", (), 2, True),
    ("support_ironing_speed", "支撑熨烫速度", "support", "float", 5, 200, 5, "mm/s", (), 0, True),

    # 树状支撑
    ("tree_support_branch_angle", "树状支撑分枝角", "support", "float", 0, 90, 1, "°", (), 0, True),
    ("tree_support_branch_diameter", "树状支撑枝径", "support", "float", 1, 20, 0.5, "mm", (), 1, True),
    ("tree_support_branch_diameter_angle", "枝径变化角", "support", "float", 0, 30, 1, "°", (), 0, True),
    ("tree_support_branch_distance", "枝间距", "support", "float", 1, 30, 0.5, "mm", (), 1, True),
    ("tree_support_wall_count", "树状支撑墙数", "support", "int", -1, 4, 1, "", (), 0, True),

    # ============================================================ 磨砂皮肤
    ("fuzzy_skin", "磨砂皮肤", "quality", "enum", 0, 0, 1, "",
     ("none", "external", "all", "all_shells"), 2, False),
    ("fuzzy_skin_thickness", "磨砂厚度", "quality", "float", 0.01, 2, 0.05, "mm", (), 2, True),
    ("fuzzy_skin_point_distance", "磨砂点距", "quality", "float", 0.05, 2, 0.05, "mm", (), 2, True),
    ("fuzzy_skin_first_layer", "首层也磨砂", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("fuzzy_skin_mode", "磨砂模式", "quality", "enum", 0, 0, 1, "",
     ("displacement", "extrusion"), 2, True),
    ("fuzzy_skin_noise_type", "磨砂噪声类型", "quality", "enum", 0, 0, 1, "",
     ("classic", "perlin", "billow", "ridged"), 2, True),
    ("fuzzy_skin_octaves", "磨砂噪声八度", "quality", "int", 1, 8, 1, "", (), 0, True),
    ("fuzzy_skin_persistence", "磨砂噪声持续度", "quality", "float", 0.1, 1, 0.05, "", (), 2, True),
    ("fuzzy_skin_scale", "磨砂噪声尺度", "quality", "float", 0.1, 5, 0.1, "", (), 2, True),

    # ============================================================ 螺旋（花瓶）模式
    ("spiral_mode", "螺旋花瓶模式", "quality", "bool", 0, 1, 1, "", (), 0, False),
    ("spiral_mode_smooth", "螺旋平滑", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("spiral_mode_max_xy_smoothing", "螺旋 XY 平滑上限", "quality", "pct", 0, 500, 10, "%", (), 0, True),

    # ============================================================ 桥接
    ("bridge_angle", "桥接方向", "speed", "float", 0, 180, 5, "°", (), 0, True),
    ("bridge_flow", "桥接流量", "speed", "float", 0.5, 2, 0.05, "×", (), 2, True),
    ("bridge_no_support", "桥接处不加支撑", "speed", "bool", 0, 1, 1, "", (), 0, True),
    ("max_bridge_length", "免支撑最大桥长", "speed", "float", 0, 200, 1, "mm", (), 0, True),
    ("thick_bridges", "厚桥接", "speed", "bool", 0, 1, 1, "", (), 0, True),
    ("internal_bridge_support_thickness", "内部桥接支撑厚度", "speed", "float", 0, 5, 0.1, "mm", (), 1, True),
    ("counterbore_hole_bridging", "沉孔桥接", "speed", "enum", 0, 0, 1, "",
     ("none", "partially_filtered", "filtered", "disabled"), 2, True),
    ("overhang_totally_speed", "全悬垂速度", "speed", "float", 5, 300, 5, "mm/s", (), 0, True),

    # ============================================================ 表面 / 壳层补充
    ("top_surface_density", "顶面密度", "infill", "pct", 10, 100, 5, "%", (), 0, True),
    ("bottom_surface_density", "底面密度", "infill", "pct", 10, 100, 5, "%", (), 0, True),
    ("bottom_surface_pattern", "底面图案", "infill", "enum", 0, 0, 1, "",
     ("monotonic", "monotonicline", "rectilinear", "concentric", "hilbertcurve"), 2, True),
    ("sub_top_surface_pattern", "次顶面图案", "infill", "enum", 0, 0, 1, "",
     ("monotonic", "monotonicline", "rectilinear", "concentric"), 2, True),
    ("top_shell_thickness", "顶层最小厚度", "quality", "float", 0, 10, 0.2, "mm", (), 1, True),
    ("bottom_shell_thickness", "底层最小厚度", "quality", "float", 0, 10, 0.2, "mm", (), 1, True),
    ("top_area_threshold", "顶面判定阈值", "infill", "pct", 0, 500, 5, "%", (), 0, True),
    ("top_solid_infill_flow_ratio", "顶面实心流量比", "infill", "array_float", 0.5, 1.5, 0.01, "", (), 2, True),
    ("top_color_penetration_layers", "顶面混色渗透层", "infill", "int", 0, 30, 1, "层", (), 0, True),
    ("bottom_color_penetration_layers", "底面混色渗透层", "infill", "int", 0, 30, 1, "层", (), 0, True),

    # ============================================================ 填充补充
    ("infill_combination", "合并填充", "infill", "bool", 0, 1, 1, "", (), 0, True, True),
    ("infill_rotate_step", "填充旋转步进", "infill", "float", 0, 360, 5, "°", (), 0, True),
    ("infill_shift_step", "填充偏移步进", "infill", "float", 0, 5, 0.1, "mm", (), 2, True),
    ("infill_lock_depth", "填充锁定深度", "infill", "int", 0, 10, 1, "层", (), 0, True),
    ("minimum_sparse_infill_area", "稀疏填充最小面积", "infill", "float", 0, 200, 1, "mm²", (), 0, True),
    ("infill_instead_top_bottom_surfaces", "用填充替代顶底面", "infill", "bool", 0, 1, 1, "", (), 0, True),
    ("sparse_infill_anchor", "稀疏填充锚固", "infill", "pct", 0, 1000, 10, "%", (), 0, True),
    ("sparse_infill_anchor_max", "锚固最大值", "infill", "float", 0, 100, 1, "mm", (), 0, True),
    ("symmetric_infill_y_axis", "Y 轴对称填充", "infill", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 速度补充
    ("gap_infill_speed", "缝隙填充速度", "speed", "array_float", 5, 500, 5, "mm/s", (), 0, True),
    ("small_perimeter_speed", "小周长速度", "speed", "array_pct", 1, 100, 5, "%", (), 0, True),
    ("small_perimeter_threshold", "小周长阈值", "speed", "array_float", 0, 100, 1, "mm", (), 0, True),
    ("vertical_shell_speed", "垂直外壳速度", "speed", "array_pct", 1, 100, 5, "%", (), 0, True),
    ("travel_speed_z", "Z 向空走速度", "speed", "array_float", 0, 100, 1, "mm/s", (), 0, True),
    ("slow_down_min_speed", "降速最低速度", "speed", "array_float", 1, 100, 1, "mm/s", (), 0, True),

    # ============================================================ 加速度 / 减速补充
    ("accel_to_decel_enable", "启用减速（accel_to_decel）", "accel", "bool", 0, 1, 1, "", (), 0, False),
    ("accel_to_decel_factor", "减速系数", "accel", "pct", 1, 100, 5, "%", (), 0, False),
    ("initial_layer_travel_acceleration", "首层空走加速度", "accel", "array_float", 100, 20000, 100, "mm/s²", (), 0, True),
    ("travel_short_distance_acceleration", "短距空走加速度", "accel", "array_float", 100, 20000, 50, "mm/s²", (), 0, True),

    # 高度降速（Z 向分段降速，抑制高件振纹）
    ("enable_height_slowdown", "启用高度降速", "accel", "array_float", 0, 1, 1, "", (), 0, True),
    ("slowdown_start_height", "降速起始高度", "accel", "array_float", 0, 1000, 5, "mm", (), 0, True),
    ("slowdown_end_height", "降速结束高度", "accel", "array_float", 0, 1000, 5, "mm", (), 0, True),
    ("slowdown_start_speed", "降速起始速度", "accel", "array_float", 0, 2000, 10, "mm/s", (), 0, True),
    ("slowdown_end_speed", "降速结束速度", "accel", "array_float", 0, 2000, 10, "mm/s", (), 0, True),
    ("slowdown_start_acc", "降速起始加速度", "accel", "array_float", 100, 100000, 100, "mm/s²", (), 0, True),
    ("slowdown_end_acc", "降速结束加速度", "accel", "array_float", 100, 100000, 100, "mm/s²", (), 0, True),

    # ============================================================ 冷却补充
    ("fan_cooling_layer_time", "风扇介入层时间", "cooling", "array_float", 0, 200, 1, "s", (), 0, False),
    ("enable_overhang_bridge_fan", "悬垂/桥接风扇", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("first_x_layer_fan_speed", "首 N 层风扇转速", "cooling", "array_float", 0, 100, 5, "%", (), 0, True),
    ("first_x_layer_part_fan_speed", "首 N 层辅助风扇", "cooling", "array_float", 0, 100, 5, "%", (), 0, True),
    ("pre_start_fan_time", "提前开风扇时间", "cooling", "array_float", 0, 30, 1, "s", (), 0, True),
    ("close_additional_fan_first_x_layers", "辅助风扇首 N 层关闭", "cooling", "array_float", 0, 20, 1, "层", (), 0, True),
    ("additional_fan_full_speed_layer", "辅助风扇全速起始层", "cooling", "array_float", 0, 20, 1, "层", (), 0, True),
    ("overhang_threshold_participating_cooling", "参与冷却的悬垂阈值", "cooling", "array_pct", 0, 100, 5, "%", (), 0, True),
    ("slow_down_for_layer_cooling", "层冷却降速", "cooling", "bool", 0, 1, 1, "", (), 0, False),
    ("slow_down_layer_time", "层冷却最短时间", "cooling", "array_float", 0, 60, 1, "s", (), 0, False),
    ("no_slow_down_for_cooling_on_outwalls", "外壁不做冷却降速", "cooling", "bool", 0, 1, 1, "", (), 0, True),
    ("cooling_slowdown_logic", "冷却降速逻辑", "cooling", "enum_array", 0, 0, 1, "",
     ("uniform_cooling", "minimum_layer_time"), 2, True),
    ("reduce_fan_stop_start_freq", "减少风扇启停", "cooling", "bool", 0, 1, 1, "", (), 0, False),
    ("auxiliary_fan", "启用辅助风扇", "cooling", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 回抽补充
    ("retract_length_toolchange", "换料回抽距离", "retraction", "array_float", 0, 20, 0.5, "mm", (), 1, True),
    ("retract_restart_extra_toolchange", "换料回填补偿", "retraction", "array_float", -2, 5, 0.1, "mm", (), 1, True),
    ("enable_long_retraction_when_cut", "切断时长回抽", "retraction", "int", 0, 2, 1, "", (), 0, True),
    ("long_retractions_when_cut", "切断长回抽参数", "retraction", "array_float", 0, 20, 0.5, "mm", (), 1, True),
    ("reduce_infill_retraction_mode", "减少填充回抽模式", "retraction", "enum", 0, 0, 1, "",
     ("Auto", "Force", "None"), 2, True),
    ("use_firmware_retraction", "使用固件回抽", "retraction", "bool", 0, 1, 1, "", (), 0, True),

    # ============================================================ 擦料塔补充
    ("prime_tower_lift_height", "擦料塔抬升高度", "tower", "float", -1, 20, 0.5, "mm", (), 1, True),
    ("prime_tower_lift_speed", "擦料塔抬升速度", "tower", "float", 1, 200, 5, "mm/s", (), 0, True),
    ("prime_tower_max_speed", "擦料塔最高速度", "tower", "float", 1, 300, 5, "mm/s", (), 0, True),
    ("prime_tower_rib_wall", "擦料塔带肋墙", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("prime_tower_rib_width", "擦料塔肋宽", "tower", "float", 1, 30, 1, "mm", (), 0, True),
    ("prime_tower_infill_gap", "擦料塔填充间隙", "tower", "pct", 0, 300, 5, "%", (), 0, True),
    ("prime_tower_skip_points", "擦料塔跳过尖角", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("wipe_tower_no_sparse_layers", "擦料塔不留稀疏层", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("flush_into_infill", "废料冲入填充", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("flush_into_objects", "废料冲入对象", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("flush_into_support", "废料冲入支撑", "tower", "bool", 0, 1, 1, "", (), 0, True),
    ("flush_multiplier", "废料倍率", "tower", "array_float", 0, 3, 0.05, "×", (), 2, True),

    # ============================================================ 其他工艺
    ("precise_z_height", "精确 Z 高度", "z", "bool", 0, 1, 1, "", (), 0, True),
    ("slicing_mode", "切片模式", "quality", "enum", 0, 0, 1, "",
     ("regular", "even-odd", "close-hole"), 2, False),
    ("slice_closing_radius", "切片闭合半径", "quality", "float", 0, 1, 0.001, "mm", (), 3, True),
    ("resolution", "切片分辨率", "quality", "float", 0.001, 0.1, 0.001, "mm", (), 3, True),
    ("min_feature_size", "最小特征尺寸", "quality", "pct", 0, 100, 1, "%", (), 0, True),
    ("enable_arc_fitting", "圆弧拟合（G2/G3）", "quality", "bool", 0, 1, 1, "", (), 0, True),
    ("print_in_clockwise", "顺时针打印", "quality", "bool", 0, 1, 1, "", (), 0, True, True),
    ("xy_hole_compensation", "孔洞 XY 补偿", "z", "float", -1, 1, 0.01, "mm", (), 2, False, True),
    ("xy_contour_compensation", "轮廓 XY 补偿", "z", "float", -1, 1, 0.01, "mm", (), 2, False),
    ("circle_compensation_manual_offset", "圆补偿手动偏移", "z", "float", -0.5, 0.5, 0.01, "mm", (), 2, True),
    ("enable_circle_compensation", "启用圆补偿", "z", "bool", 0, 1, 1, "", (), 0, True),
]
