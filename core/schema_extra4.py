"""参数表第四批：收缩/孔洞补偿系数、切断回抽距离、多材料分段互锁、走线起终点。

补完这批后，除「硬件定义 / 温度 / 多材料槽位 / G 代码 / 元数据」这五类
结构上不应由调参工具改动的键以外，Bambu Studio 工程里所有可调切片参数都已在表内。
"""

EXTRA_PARAMS_4: list[tuple] = [
    # ---- 收缩 / 孔洞补偿系数（Bambu 的 XY 补偿曲线参数，12 项一组）
    # 用户按自己喷嘴/耗材标定过，preserve=True = 保留用户值不被默认值覆盖
    ("counter_coef_1", "外径补偿系数 1", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("counter_coef_2", "外径补偿系数 2", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("counter_coef_3", "外径补偿系数 3", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("counter_limit_max", "外径补偿上限", "z", "float", 0, 50, 0.1, "mm", (), 2, True, True),
    ("counter_limit_min", "外径补偿下限", "z", "float", -50, 50, 0.1, "mm", (), 2, True, True),
    ("hole_coef_1", "孔洞补偿系数 1", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("hole_coef_2", "孔洞补偿系数 2", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("hole_coef_3", "孔洞补偿系数 3", "z", "float", -2, 2, 0.0001, "", (), 4, True, True),
    ("hole_limit_max", "孔洞补偿上限", "z", "float", -50, 50, 0.1, "mm", (), 2, True, True),
    ("hole_limit_min", "孔洞补偿下限", "z", "float", -50, 50, 0.1, "mm", (), 2, True, True),

    # ---- 切断 / 换料回抽距离
    ("retraction_distances_when_cut", "切断时回抽距离", "retraction", "array_float", 0, 20, 0.5, "mm", (), 1, True),
    ("long_retractions_when_ec", "换料时长回抽", "retraction", "array_float", 0, 20, 0.5, "mm", (), 1, True),
    ("retraction_distances_when_ec", "换料时回抽距离", "retraction", "array_float", 0, 20, 0.5, "mm", (), 1, True),

    # ---- 多材料分段互锁（H2D 系列）
    ("mmu_segmented_region_interlocking_depth", "分段互锁深度", "wall", "int", 0, 20, 1, "层", (), 0, True),
    ("mmu_segmented_region_max_width", "分段最大宽度", "wall", "float", 0, 100, 1, "mm", (), 1, True),

    # ---- 走线起终点点位
    # 工程里存的是用户手动指定的坐标（形如 ["30x-3","54x245"]），
    # 不是 "auto"/"custom" 这类枚举。preserve=True = 永远不覆盖用户的走线设置。
    ("start_end_points", "走线起终点配置", "seam", "enum", 0, 0, 1, "",
     ("auto", "custom"), 2, True, True),

    # ---- 体积流量自适应系数
    # 官方写法是空格分隔的 6 元素向量：["0 0 0 0 0 0"]，不是标量。
    # vec_float 类型让 parse/format 原样保留这一串，不会被拆坏。
    ("volumetric_speed_coefficients", "体积流量自适应系数", "flow", "vec_float", -72, 85, 0.01, "", (), 3, True, True),
    ("filament_max_volumetric_speed", "耗材体积流量上限", "flow", "array_float", 0, 100, 0.5, "mm³/s", (), 2, True, True),
]
