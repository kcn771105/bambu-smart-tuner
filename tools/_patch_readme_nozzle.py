import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()

section = '''### 7.5 喷嘴流量同步（换喷嘴必须换流量）

Bambu 官方的 `filament_max_volumetric_speed` 是**按喷嘴**给的，不是按耗材：

| 耗材 | 机型组 | 0.2 喷嘴 | 0.4 喷嘴 | 0.6 喷嘴 | 0.8 喷嘴 |
| --- | --- | --- | --- | --- | --- |
| PLA | X1 / P1 / P2 / A1 | 2 | 21 | 21 | 21 |
| PLA | H2 | 2 | 25 | 30 | 30 |
| PETG | X1 / P1 | 1 | 13 | 13 | 16 |
| PETG | P2 | 1 | 13 | 16 | 16 |
| PETG | A1 | 1 | 9 | 9 | 12 |
| PETG | H2 | 1 | 13 | 16 | 16 |
| ABS | X1 / P1 / P2 | 2 | 16 | 16 | 18 |
| ABS | A1 | 2 | 16 | 16 | 16 |
| ABS / ASA | H2 | 2 | 20 | 25 | 25 |
| ASA | X1 / P1 / P2 / A1 | 2 | 18 | 18 | 18 |
| TPU | 全系 | 3.6 | 3.6 | 3.6 | 3.6 |

（数据由 `tools/_dump_flow_matrix2.py` 从官方预设读出，写进 `rules/BambuRules.json` 的
`nozzle_flow` 段。改喷嘴时引擎读它折算。）

为什么必须同步：0.2 喷嘴的熔池每秒只能熔 1 mm³ 料。把 0.4 的 13 mm³/s 套到 0.2 上，
算出来的内壁 200 mm/s 是物理跑不到的 —— 实际表现是挤出不足、表面糊、严重时堵料。
反过来把 0.2 的 1 套到 0.8 上，会把 0.8 的产能白白压掉 90%。

引擎的处理（`core/nozzle_flow.py` + `core/rules_engine.py` 的 `_clamp_flow`）：

1. 工程里的 `filament_max_volumetric_speed` 是按**工程那个喷嘴**标定的；
2. 你在下拉里换了喷嘴 → 先按官方流量比把工程标定值折算到新喷嘴；
3. 再与新喷嘴的官方上限**取小**；
4. 都记一条警告，写清「18 mm³/s 是按 0.4 标的 → 折算到 0.2 是 1.4 → 与官方 1 取小 → 按 1.0 算」。

实测（鱼缸温度计支架，P2S + PETG，工程标定 18 mm³/s、工程喷嘴 0.4）：

| 你在下拉里选 | 采用流量上限 | 外壁 | 内壁 | 填充 | 层高 | 线宽 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.2 mm | **1.0** mm³/s | 47.6 | 44.4 | 44.4 | 0.10 | 0.21 |
| 0.4 mm（= 工程值） | 18.0 mm³/s | 161.5 | 200.0 | 200.0 | 0.20 | 0.42 |
| 0.6 mm | **16.0** mm³/s | 90.7 | 84.7 | 84.7 | 0.28 | 0.63 |
| 0.8 mm | **16.0** mm³/s | 68.0 | 63.5 | 63.5 | 0.28 | 0.84 |

同喷嘴时仍以你工程里的实测标定为准（那是这台机器 + 这卷料的真实值），
只有换了喷嘴才会被官方上限压住 —— 因为你的标定只对原喷嘴成立。

验证命令：

```bash
python tools/check_nozzle_flow.py      # 四个喷嘴各跑一遍，打印流量上限与关键速度
python -m pytest tests/test_nozzle_flow.py -q
```

'''

anchor = "### 7.3 时长预算（每档自带，写在 JSON 里）"
assert anchor in s
s = s.replace(anchor, section + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("README 增 7.5 喷嘴流量同步，长度", len(s))
