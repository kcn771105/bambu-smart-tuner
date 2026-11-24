import io

# ---------- 1. 报告加「热端流量类型」 ----------
p = "core/report.py"
s = io.open(p, encoding="utf-8").read()
old = 'if getattr(result, "plate", ""):'
assert old in s
s = s.replace(old, 'if getattr(result, "hotend", ""):\n'
                     '        add(f"- {result.hotend}")\n'
                     '    if getattr(result, "plate", ""):', 1)
io.open(p, "w", encoding="utf-8").write(s)
print("report：加热端流量类型")

# ---------- 2. README 新增章节 ----------
r = "README.md"
t = io.open(r, encoding="utf-8").read()
anchor = "## 8"
i = t.find(anchor)
if i < 0:
    i = len(t)
section = """## 7.9 热端流量类型（标准流量 / 高流量 / E3D 高流量）

### 为什么它不能只当标签

三种热端的差别是**熔化能力**，不是精度。同一个 0.4 喷嘴，标准热端官方标定 PETG 13 mm³/s，
高流量热端能推得更多。如果只把它显示在界面上、不影响计算，高流量热端就会被按标准热端的
流量上限钳着跑，白买了。

### 怎么识别

工程里表达这件事的键有六个（都在机器页，只读）：

| 键 | 典型值 | 说明 |
| --- | --- | --- |
| `nozzle_volume_type` | `["Standard"]` | 首选判据 |
| `default_nozzle_volume_type` | `["Standard"]` | 兜底 |
| `extruder_nozzle_stats_new` | `["Standard#1"]` | 带数量后缀 |
| `extruder_nozzle_stats` | `["Standard#1"]` | 同上 |
| `printer_extruder_variant` | `["Direct Drive Standard", "Direct Drive High Flow", ...]` | 整机支持的变体 |
| `print_extruder_variant` | 同上 | 本工程用的变体 |
| `nozzle_volume` | `["110","110","110"]` | 熔池体积，随类型变化 |

识别顺序就是上表顺序，命中即停；`core/hotend.py` 的 `detect()` 会把「依据哪个键、原值是什么」
一起记下来，显示在界面与报告里（`依据 nozzle_volume_type = 'Standard'`），方便你判断识别对不对。

### 怎么算

规则库 `hotend_flow.types` 只给一个倍率 `volumetric_mul`：

```json
"hotend_flow": {
  "types": {
    "standard": { "label": "标准流量",   "volumetric_mul": 1.0 },
    "high":     { "label": "高流量",     "volumetric_mul": 1.35 },
    "e3d":      { "label": "E3D 高流量", "volumetric_mul": 1.55 }
  }
}
```

- 倍率**只会放宽、不会收紧**（`factor()` 强制 ≥ 1.0）：识别不出来时按 1.0，不会把高流量热端压回去。
- 它作用在**体积流量上限**上，不额外乘速度。高流量省下的时间由「流量上限 ↑ → `_clamp_flow`
  允许更快的速度」自动体现；再单独乘速度倍率等于同一件事算两遍，会让速度越过机器上限，
  也会把时长估算压低得不真实。
- 工程里的 `filament_max_volumetric_speed` 是**在工程那根热端上标出来的**。如果你在下拉里
  改成高流量（= 换了热端），引擎会按两根热端的比例折算这个标定值，并给一条警告提醒你
  换热端后重新做一次流量标定。

### 实测（真实工程 P2S + PETG，工程标定 18 mm³/s）

| 下拉选择 | 流量上限 | 内壁速度 | 层高 |
| --- | --- | --- | --- |
| 自动 / 标准流量 | 18.0 | 200.0 | 0.20 |
| 高流量 | 24.3 | 234.8 | 0.23 |
| E3D 高流量 | 27.9 | 269.6 | 0.23 |

"""
t = t[:i] + section + t[i:]
io.open(r, "w", encoding="utf-8").write(t)
print("README 增 §7.9，长度", len(t))
