import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()
if "§7.17" in s or "## 7.17" in s:
    print("已有支撑章节")
else:
    section = """## 7.17 支撑：按模型实测尺寸算，且只有一个模块说了算

以前支撑参数被三个地方同时写（形状原型、几何规则、支撑策略），结果出现两种毛病：
**支撑明明没开，却改了支撑间隙**；以及同一个键被三方各写一次、互相覆盖。

现在分工是硬边界：

| 模块 | 只负责 | 产出 |
| --- | --- | --- |
| `core/support_plan.py` | 要不要支撑、悬垂判定角多少 | `enable_support`、`support_threshold_angle` 两个键 |
| `core/support_model.py` | 用多少料、离多远、长什么样、多快 | 全部支撑定量键 |
| `core/shape_rules.py` / `core/geom_rules.py` | 不再写任何 `support_*` | — |

引擎在 7.76 层之后有一道**白名单兜底**：不管上游哪一层写过支撑键，只要不是
`support_model.tune()` 算出来的，一律从待写列表里撤回。所以「支撑没开」时
连一个 `support_*` 键都不会写进文件。

### 八组规则（全部用模型实测值）

| 参数 | 依据 | 规则 |
| --- | --- | --- |
| 支撑线距 `support_base_pattern_spacing` | 悬垂总面积 | ≥4000→1.6、≥1500→2.0、≥400→2.5、其余 3.0 mm |
| 顶面间隙 `support_top_z_distance` | 层高 | 层高×0.7，夹 0.12~0.30 |
| 底面间隙 `support_bottom_z_distance` | 层高 | 层高×1.0，夹 0.15~0.35 |
| 水平间距 `support_object_xy_distance` | 细高比/高/底面积 | 细高比≥3 或高≥120→0.8；底面积<600 mm²→0.9；其余 0.5 |
| 接触面层数 `support_interface_top_layers` / `_bottom_layers` | 悬垂面积 | 大面积 3 层 / 零星 2 层 |
| 接触面线距 `support_interface_spacing` | 悬垂面积 | 大面积 0.5（求平整）/ 零星 0.7（求好撕） |
| 支撑线宽 `support_line_width` | 线宽基准 | ×0.9（细一点更好撕） |
| 支撑形态 `support_type` / `support_style` | 细高比、高度 | 细高比≥3.2 或高≥150 → tree(auto)；≥3.5 用 tree_strong，否则 tree_slim；大面积低矮悬垂 → normal(auto)+grid |
| 支撑速度 `support_speed` / `support_interface_speed` | 机型上限 × 模式 | 本体 ×0.55~0.85；接触面 = 本体 ×0.45~0.70（质量档最慢） |
| 质量向（quality/fine/ultrafine） | 模式 | `support_critical_regions_only=1` + 支撑熨烫（流量 10%、线距 0.15） |
| 草稿档 | 模式 | `support_remove_small_overhang=1` |

### 实测（P2S + PETG，32×45×54、悬垂 644 mm²、细高比 6.36）

```
strength  → 8 项：线宽 0.38｜速度 500｜顶隙 0.14｜水平距 0.9｜tree_strong｜
           界面线距 0.7｜界面速度 300｜enable_support 1
balanced  → 0 项（该模型不需要支撑，一个键都不写）
quality   → 11 项（含判定角 25°、底隙 0.15、critical_regions_only 1）
draft     → 1 项（只有判定角 35°）
```

不带模型几何（只看配置文件）时只剩 `enable_support` / `support_threshold_angle` —— 
这是刻意的：没有几何就别猜密度。

### 想改支撑策略

改 `rules/BambuRules.json` 管不到支撑定量了（那是代码里的模型公式）。
要调阈值就改 `core/support_model.py` 顶部的 `MODE_SPEED` / `MODE_IFACE` 与
`spacing_for()`，或者把 `support_policy` 里的判定角阈值调掉。
"""
    s = s.rstrip() + "\n\n" + section
    io.open(p, "w", encoding="utf-8").write(s)
    print("README 增支撑章节，长度", len(s))
