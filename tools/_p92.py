"""把 shape_rules 里写死的 support_* 定量 op 清掉（只保留 enable_support 的 keep 语义）。

理由：支撑的定量参数现在唯一由 core/support_model.py 决定，
两边都写会互相覆盖（实测：支撑没开却改了 support_top_z_distance）。
MERGE_DIR / 前缀判定表里的条目保留（那只是合并方向说明，不产生写入）。
"""
import io
import re

p = "core/shape_rules.py"
s = io.open(p, encoding="utf-8").read()

# 只删「行首是缩进 + "support_xxx": {...}」这种真正的 op 定义；
# MERGE_DIR 里的形式是 "support_xxx": "min"，不是 dict，不会被误删。
pattern = re.compile(r'^\s*"(support_[a-z_]+|tree_support_[a-z_]+)":\s*\{"[^{}]*\}\s*,?\s*$')
lines = s.split("\n")
kept, dropped = [], []
for ln in lines:
    if pattern.match(ln):
        dropped.append(ln.strip())
    else:
        kept.append(ln)

s2 = "\n".join(kept)

# 删完可能留下连续空行，压一下
s2 = re.sub(r"\n{3,}", "\n\n\n", s2)

io.open(p, "w", encoding="utf-8").write(s2)
print(f"shape_rules：删除 {len(dropped)} 行 support op")
for d in dropped:
    print("   -", d)
