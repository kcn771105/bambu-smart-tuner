import io

p = "core/report.py"
s = io.open(p, encoding="utf-8").read()

old = """    add(f"- 喷嘴：**{result.nozzle:g} mm**")"""
new = """    add(f"- 喷嘴：**{result.nozzle:g} mm**")
    if result.flow_limit:
        add(f"- 体积流量上限：**{result.flow_limit:g} mm³/s**"
            f"（已按 {result.nozzle:g} 喷嘴标定折算）")
    hw_proj = getattr(result, "project_nozzle", None)
    if hw_proj and abs(float(hw_proj) - float(result.nozzle)) > 1e-6:
        add(f"- **喷嘴已更换**：工程里装的是 {float(hw_proj):g} mm，本次按 "
            f"{result.nozzle:g} mm 计算；层高/线宽等比缩放，体积流量上限按官方"
            f"「耗材 × 机型 × {result.nozzle:g} 喷嘴」标定重新折算过"
            f"（换喷嘴不换流量，0.2 喷嘴会被按 0.4 的流量算速度，物理跑不到）。")"""
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("report 已增喷嘴流量行")
