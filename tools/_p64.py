import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()
anchor = "\n## 8"
i = s.find(anchor)
if i < 0:
    i = len(s)

section = """
## 7.15 交替额外墙层与「墙层数 / 垂直外壳厚度」的成套要求

在 Bambu Studio 里勾上 **交替额外墙层（alternate_extra_wall）** 后打开工程，Studio 会弹：

```
为使交替额外墙层正常工作，建议进行以下调整：
- 将确保垂直外壳厚度设为「部分」
- 将墙层数设为 2
是 - 应用修改并保持交替额外墙层启用
否 - 保持当前设置并启用交替额外墙层
```

这不是我们写坏了文件，是 Studio 对这三个键的一致性要求：

| 键 | 要求 |
| --- | --- |
| `alternate_extra_wall` | 1（开启） |
| `ensure_vertical_shell_thickness` | `partial`（部分）|
| `wall_loops` | 2 |

而强度档会把 `wall_loops` 从 2 提到 4~6 圈（细高件还按壁厚算到 6），必然撞上这条。

### 现在的处理（`core/wall_compat.py`，引擎第 7.77 层）

| 情况 | 处理 | 说明 |
| --- | --- | --- |
| 工程开着交替额外墙 + 本档把墙层数提到 >2 | **写出 `alternate_extra_wall = 0`** 并在日志给黄色警告 | 4 圈以上时交替额外墙的增量已经很小，外壳强度由墙圈数本身提供；想保留这个功能就用均衡档（不动墙层数） |
| 工程开着交替额外墙 + 墙层数保持 2 | **写出 `ensure_vertical_shell_thickness = partial`**，附说明 | 补齐 Studio 要求的另一半，打开工程不再弹窗 |
| 工程本来就成套（已是 partial） | 不动，只记一条 note | |
| 工程没开这个功能 | 三个键都不碰 | 原有行为不变 |

对应测试：`tests/test_hotend_safety.py::TestWallCompat`（6 项），覆盖上面四种情况 + schema 里必须有 `partial` 选项 + 引擎端到端写 0 并告警。

### 遇到这个弹窗怎么选

- 点 **是**：Studio 会把垂直外壳厚度改成「部分」、墙层数改回 **2**，等于把你刚调好的强度档墙圈数冲掉，不推荐。
- 点 **否**：保留你当前设置，交替额外墙继续开着，但 Studio 提示仍会在下次打开时出现。
- 更省事的做法：重新用本工具跑一遍（现在会自动把 `alternate_extra_wall` 写 0），或者在 Studio 里自己把那勾去掉。

### schema 里的选项修正

`ensure_vertical_shell_thickness` 的合法值是 `enabled / disabled / partial`（原来写成 `ensure_all` 是错的，Bambu 2.x 根本没有这个值），已修正，否则引擎想写「部分」会被自己的区间检查拦下来。
"""

s = s[:i] + section + s[i:]
io.open(p, "w", encoding="utf-8").write(s)
print("README 增 §7.15，长度", len(s))
