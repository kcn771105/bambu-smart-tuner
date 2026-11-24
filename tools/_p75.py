import io

# 1) schema 单一入口：UI/报告 说明「整槽写入」
p = "core/report.py"
s = io.open(p, encoding="utf-8").read()
if "分槽" not in s:
    anchor = "## 只读参数"
    note = """## 数组型参数（按热端变体分槽）

Bambu 的 `outer_wall_speed`、`inner_wall_speed`、`*_acceleration`、`travel_speed` 这类键
在工程里是数组，一个槽位对应一种热端：

```
["200", "500", "500"]     # 标准流量 / 高流量 / E3D 高流量
```

Bambu Studio 显示的是**当前所选热端**那一槽的值。只改第 0 槽时，如果你的 Studio 里
选的是「高流量」，它会读第 1 槽，看起来就像「速度没改」。所以本程序现在把这些键的
**每一槽都写成优化后的同一个值**（保守值，任何热端下都生效）；没有变体列表的工程
仍然只改第 0 槽。

"""
    if anchor in s:
        s = s.replace(anchor, note + anchor, 1)
        io.open(p, "w", encoding="utf-8").write(s)
        print("report 增加分槽说明")
    else:
        print("没找到锚点，跳过 report")
else:
    print("report 已有分槽说明")

# 2) Studio 定位表：hidden 的说明补「开发者模式」
p2 = "core/studio_ui.py"
s2 = io.open(p2, encoding="utf-8").read()
if "开发者模式" not in s2:
    s2 = s2.replace('return f"Studio 界面没有（{self.note}）"',
                    'return f"Studio 界面没有（含开发者模式）：{self.note}"', 1)
    io.open(p2, "w", encoding="utf-8").write(s2)
    print("studio_ui 隐藏项文案带上开发者模式")
else:
    print("studio_ui 已带开发者模式")
