import io

p = "core/support_model.py"
s = io.open(p, encoding="utf-8").read()
old = 'f"本体 {spd:g} ／ 接触面 {ispd:g} mm/s"))'
new = 'f"本体 {spd:g} ／ 接触面 {ispd:g} mm/s（最终还要受体积流量上限钳制）"))'
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("支撑速度文案已补")
