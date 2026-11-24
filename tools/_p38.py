import io
import re

# ---------- 1. shape_rules：删掉写死的 brim_width 绝对值，交给 core/adhesion.py 定量 ----------
p = "core/shape_rules.py"
s = io.open(p, encoding="utf-8").read()
before = len(re.findall(r'"brim_width": \{"set"', s))
s = re.sub(r'[ \t]*"brim_width": \{"set": [\d.]+},\n', "", s)
after = len(re.findall(r'"brim_width": \{"set"', s))
io.open(p, "w", encoding="utf-8").write(s)
print(f"shape_rules 删掉 {before - after} 条写死的 brim_width（剩 {after} 条）")

# ---------- 2. geom_rules：两条 brim 下限改成占位（不再和定量层抢） ----------
q = "core/geom_rules.py"
g = io.open(q, encoding="utf-8").read()
g = g.replace('_r("brim_width", "flat_lt_0_25", {"min": 8},',
              '_r("brim_width", "flat_lt_0_25", {"mul": 1.0},', 1)
g = g.replace('_r("brim_width", "small_footprint", {"min": 10},',
              '_r("brim_width", "small_footprint", {"mul": 1.0},', 1)
g = g.replace('"裙边宽度跟随形状档"', '"裙边宽度由「裙边定量」层按倾覆指数决定"', 1)
io.open(q, "w", encoding="utf-8").write(g)
print("geom_rules 两条 brim 下限改为占位")
