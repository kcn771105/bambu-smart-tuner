import json
import zipfile
from pathlib import Path

SRC = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
GEN = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架_optimized_20261124_123534.3mf")

KEYS = ["layer_height", "wall_loops", "outer_wall_speed", "sparse_infill_density",
        "sparse_infill_pattern", "inner_wall_speed", "travel_speed",
        "top_surface_speed", "brim_width", "elefant_foot_compensation"]


def load(p: Path) -> dict:
    with zipfile.ZipFile(p) as z:
        name = [n for n in z.namelist() if n.endswith("project_settings.config")][0]
        return json.loads(z.read(name).decode("utf-8"))


a, b = load(SRC), load(GEN)
print(f"原 {len(a)} 键 / 用户手里那份 {len(b)} 键")
diff = [k for k in sorted(set(a) & set(b)) if a[k] != b[k]]
print(f"两者不同的键：{len(diff)} 项")
for k in diff[:40]:
    print(f"  {k:36} {a[k]!r:26} -> {b[k]!r}")

print("\n关键键对照：")
for k in KEYS:
    print(f"  {k:30} 原 {a.get(k)!r:26} 新 {b.get(k)!r}")

print("\n新文件里的 *_settings_id：")
for k in sorted(b):
    if k.endswith("_settings_id") or "profile" in k or "preset" in k:
        print(f"  {k:34} = {b[k]!r}")
print("\n原文件里的 *_settings_id：")
for k in sorted(a):
    if k.endswith("_settings_id"):
        print(f"  {k:34} = {a[k]!r}")
