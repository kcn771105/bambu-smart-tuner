import io

r = "README.md"
t = io.open(r, encoding="utf-8").read()
i = t.find("## 8")
if i < 0:
    i = len(t)

section = """## 7.12 逐项可改性核对（269 个工艺键，一个不漏地测过）

不是「看代码觉得能改」，是**扰动→写盘→重新打开→逐键比对**跑出来的。
脚本：`python tools/audit_writable.py`，报告落在 `shots/writable_audit.md`。

| 指标 | 数值 |
| --- | --- |
| 工艺页登记键 | 269 |
| 本工程里实际存在的键 | 263 |
| **改得动、且会写进 `different_settings_to_system`（Studio 会采用）** | **263 / 263** |
| 写盘后重新打开值不一致 | 0 |
| 写进去了但没声明（Studio 会忽略） | 0 |
| 扰动不出新合法值（枚举只有一项等） | 0 |
| schema 未登记 | 0 |

测法：每个键按自己的类型造一个新值（浮点试 ×1.12 / ×0.85 / ±1 / 区间中点，百分比 ±5，
布尔取反，枚举换另一项，数组只改第 0 槽），写进 3mf、重新打开、和期望值比，
再检查它有没有出现在工艺差异声明里。

### preserve 的 9 个键：能改，但默认不动

`brim_width` `brim_object_gap` `infill_combination` `inner_wall_acceleration`
`print_in_clockwise` `smooth_coefficient` `sparse_infill_acceleration`
`start_end_points` `wall_generator`

`preserve=True` 的语义是「规则库默认不去覆盖你在 Studio 里调好的值」——不是写不进去。
形状层/几何层判定到有必要时（`allow_preserve=True`）照样会改。这 9 个键在
`audit_writable.py` 里同样跑过扰动+写盘+回读，263/263 里包含它们。

### 工程里没有的 6 个键：Bambu 根本不用

| 键 | 官方 227 个 process 预设里出现次数 |
| --- | --- |
| `bridge_acceleration` | 0 |
| `elefant_foot_compensation_layers` | 0 |
| `internal_solid_infill_acceleration` | 0 |
| `support_density` | 0 |
| `top_bottom_infill_wall_overlap` | 0 |
| `only_one_wall_top` | 1 |

前 5 个是 Orca Slicer / PrusaSlicer 的键名，Bambu 用另一套（`support_density` 对应
`support_base_pattern_spacing` + `support_interface_spacing`，`top_bottom_infill_wall_overlap`
对应 `top_bottom_infill_wall_overlap` 之外的重叠键）。写进去 Studio 也不认，
所以工具直接跳过并在报告里写明，不假装改过。

### 这轮补上的 4 条覆盖（原来「从不主动调」的键）

| 键 | 加在哪 | 为什么 |
| --- | --- | --- |
| `wall_generator = arachne` | `shape_profiles.thin_wall` / `small_detail` 三档 | 薄壁件用经典墙算法会漏掉窄于线宽的区域，Arachne 能变线宽填满 |
| `infill_combination = true` | `modes.quality.ops` | 同层相邻填充合并成长线，少空走、少拉丝 |
| `inner_wall_acceleration = 0` | `modes.strength.ops` | 0 = 跟随默认加速度；内壁看不见，强度档没必要为它付时间 |
| `brim_object_gap = 0.3` | 新交叉规则 `brim-gap-adhesion`（`brim_width > 0` 时） | 裙边留 0.3 mm 间隙，撕裙边不带下首层 |

规则库主动引用 266 / 269。剩下 3 个是刻意不动：`print_in_clockwise`（绕行方向，纯偏好）、
`smooth_coefficient`（平滑算法强度，没有客观最优）、`sparse_infill_acceleration`
（强度档抬高会与体积流量上限打架，交给 8d 钳制更稳）。

"""
t = t[:i] + section + t[i:]
io.open(r, "w", encoding="utf-8").write(t)
print("README 增 §7.12，长度", len(t))
