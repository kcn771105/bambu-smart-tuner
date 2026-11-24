# 工艺页逐项可改性核对

- 工艺页登记键：269
- 工程里存在：263
- **改得动且会声明（Studio 会采用）：263**
- 写盘后值不一致：0
- 写进去了但没声明：0
- 明确 preserve（故意不改）：9
- 扰动不出新值（枚举只有一项等）：0
- 工程里没有该键：6
- schema 未登记：0

## preserve（设计上不写）（9）

- `brim_object_gap`
- `brim_width`
- `infill_combination`
- `inner_wall_acceleration`
- `print_in_clockwise`
- `smooth_coefficient`
- `sparse_infill_acceleration`
- `start_end_points`
- `wall_generator`

## 工程里没有该键（6）

- `bridge_acceleration`
- `elefant_foot_compensation_layers`
- `internal_solid_infill_acceleration`
- `only_one_wall_top`
- `support_density`
- `top_bottom_infill_wall_overlap`

官方 227 个 process 预设里它们的出现次数：

- `bridge_acceleration`：0 次（Bambu 不用这个键名，写了也不会生效）
- `elefant_foot_compensation_layers`：0 次（Bambu 不用这个键名，写了也不会生效）
- `internal_solid_infill_acceleration`：0 次（Bambu 不用这个键名，写了也不会生效）
- `only_one_wall_top`：1 次
- `support_density`：0 次（Bambu 不用这个键名，写了也不会生效）
- `top_bottom_infill_wall_overlap`：0 次（Bambu 不用这个键名，写了也不会生效）

## 规则库是否会用它们

- 被规则库任一层引用：266 / 269
- 规则库从不主动调的（仍可手工在 Studio 里改，工具不会碰）：
  - `print_in_clockwise`
  - `smooth_coefficient`
  - `sparse_infill_acceleration`
