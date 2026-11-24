import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()

section = '''### 7.6 打印板同步（板型 / 板面 / 放得下吗）

工程里带着三组和板有关的信息，本程序全部读、全部判，板型和板面本身只读不写：

| 来自哪 | 键 | 例子 |
| --- | --- | --- |
| 打印页 | `curr_bed_type` | `Supertack Plate` |
| 耗材页 | `cool_plate_temp` / `eng_plate_temp` / `hot_plate_temp` / `textured_plate_temp` / `supertack_plate_temp` | 本工程 PETG：0 / 70 / 70 / 80 / 60 |
| 机器页 | `printable_area` / `printable_height` / `wrapping_exclude_area` | 256×256×256，前方禁打区 1 块 |

**兼容性判据直接用官方数据**：官方 filament 预设里，某条料在某块板上不可用时，
那块板的温度就是 `0`。本工程 PETG 的 `cool_plate_temp = 0` —— 说明低温板不能跑 PETG。
所以看到 0 就报硬警告，不用自己编一张兼容表。

引擎第 7.8 层做四件事：

1. 认板型：`core/plate.py` 把 `curr_bed_type` 对应到官方温度键（「光面 PEI」复用纹理板温度键）；
2. 判兼容：温度 `0` → 硬警告「这条料不能在这个板上打印」；
3. 判板面：工程 `printable_area` 与机型官方板面对不上就报警 —— 这是**机型识别错**的强信号
   （例如识别成 A1 mini 但工程板面是 256×256，A1 mini 只有 180×180）；
4. 判放得下：用**你选的那台机器**的官方板面比每件的 `size_x × size_y`，两个方向都试（含旋转 90°）。

机型官方板面（写进 `rules/BambuRules.json` 的 `printers[*].bed`）：

| 机型 | 板面 | 成型高度 |
| --- | --- | --- |
| X1 / X1C / X1E / P1P / P1S / P2S / P2P / A1 | 256 × 256 | 256 |
| A1 mini | **180 × 180** | 180 |
| H2D / H2D Pro | **350 × 320** | 325 |
| H2S | **340 × 320** | 340 |

板型相关工艺微调写在 `rules/BambuRules.json` 的 `plates.items.<板型>.process`，
默认只给一条（超粘板 `elefant_foot_compensation ≥ 0.15`，因为粘得越牢越容易鼓边）。
注意：`brim_width` 在 schema 里是 `preserve=True`（你自己定的值不许动），板层写它会被静默跳过 ——
所以「超粘板别加宽裙边」这类建议以 `advice` 文字形式进日志，不动参数。

验证：

```bash
python tools/check_plate.py        # 正常 / 低温板不兼容 / 机型板面对不上 三种情形
python -m pytest tests/test_plate.py -q
```

'''

anchor = "## 8. 测试"
assert anchor in s
s = s.replace(anchor, section + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("README 增 7.6 打印板同步，长度", len(s))
