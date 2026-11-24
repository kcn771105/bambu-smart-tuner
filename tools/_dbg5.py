import io
import re

for path in ("core/shape_rules.py", "core/geom_rules.py", "core/support_plan.py"):
    s = io.open(path, encoding="utf-8").read()
    keys = sorted(set(re.findall(r'"(support[a-z_]*|enable_support|tree_support[a-z_]*)"', s)))
    print(f"{path}: {len(keys)}")
    for k in keys:
        print("   ", k)
    print()
