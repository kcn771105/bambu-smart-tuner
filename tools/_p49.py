import io

r = "README.md"
t = io.open(r, encoding="utf-8").read()

section = """## 7.14 改完以后在 Bambu Studio 里怎么找到它

表格里改一项，回 Studio 找不到对应开关，是这套工具最常被问的问题。现在每个参数都带定位：

**参数对比表新增一列「Studio 里在哪」**，格式是 `页签 › 分组`：

| 参数 | Studio 里在哪 |
| --- | --- |
| 层高 | 质量 › 层高 |
| 墙层数（外壁+内壁） | 强度 › 墙层数 |
| 外壁速度 | 速度 › 其他层速度 |
| 空走速度 | 速度 › 移动速度 |
| 裙边宽度 | 多材料 › 裙边 |
| 支撑主体线距 | 支撑 › 间距 |
| 熨烫流量 | 质量 › 熨烫 |

**怎么用**：在那一行上右键 → 「复制 Studio 搜索词」，到 Studio 工艺面板顶部的搜索框里粘上，
它就直接跳到这条设置（搜索词是 Studio 自己的叫法，例如 `墙层数（Wall loops）`）。

### 数据从哪来

`data/studio_ui.json`，由 `tools/gen_studio_ui.py` 生成，三路合成：

1. **官方词条自动匹配**（141 条）：读 `C:\\Program Files\\Bambu Studio\\resources\\i18n\\zh_CN\\BambuStudio.mo`，
   把 4300 条「英文 UI 名 → 中文 UI 名」按键名归一后匹配，拿到 Studio 里真正的叫法；
2. **手工对照**（88 条）：mo 里没有、或叫法差太远的（如 `default_acceleration` → 加速度 › 默认
   `Normal printing`），在 `tools/gen_studio_ui.py` 的 `OVERRIDES` 里写死；
3. **标明界面没有**（38 条）：`conformal_*`、`interlocking_*`、`accel_to_decel_*`、`mmu_segmented_*`、
   `start_end_points` 这类键，Studio 工艺面板确实没有开关，表格里显示
   「Studio 界面没有（原因）」并标黄，避免你去界面上白找。

页签按**键名前缀**推断（`brim_/skirt_/prime_tower_` → 多材料，`support_/tree_support_/raft_` → 支撑，
`*_speed/*_acceleration` → 速度，`wall_/top_shell/sparse_infill` → 强度，`seam_/ironing_/elefant_foot` → 质量），
不是拍脑袋：Bambu 的界面分组就是按这个规律排的。

### 自己补一条

新的键（比如以后 Bambu 加了参数）出现在表格里但没有名字时：

1. 在 Studio 里找到那条设置，记下中文名与英文名；
2. 打开 `tools/gen_studio_ui.py`，往 `OVERRIDES` 里加一行
   `"你的键名": ("页签", "分组", "中文名", "English name"),`；
3. 跑 `python tools/gen_studio_ui.py` 重新生成 `data/studio_ui.json`；
4. 打包后的版本改 `dist\\data\\studio_ui.json` 也行（EXE 优先读同目录这份）。

报告（导出 Markdown）里的参数对比表同样带这一列，发给别人看也知道在哪改。

"""
i = t.find("## 8")
if i < 0:
    i = len(t)
t = t[:i] + section + t[i:]
io.open(r, "w", encoding="utf-8").write(t)
print("README 增 §7.14，长度", len(t))
