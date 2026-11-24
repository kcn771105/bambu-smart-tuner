"""拉出「耗材 × 喷嘴」的官方流量矩阵（Bambu 官方 filament 预设沿 inherits 合并）。"""
import io
import json
import os
import re

FIL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\filament"


def resolve(name, seen=None):
    seen = seen or set()
    if name in seen:
        return {}
    seen.add(name)
    p = os.path.join(FIL, name + ".json")
    try:
        with io.open(p, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    parent = raw.pop("inherits", None)
    out = {}
    if parent:
        out.update(resolve(parent, seen))
    out.update(raw)
    return out


FAM = ["PLA Basic", "PETG Basic", "ABS", "ASA", "TPU 95A"]
NOZ = ["0.2", "0.4", "0.6", "0.8"]
MACH = ["X1C", "P2S", "A1", "H2D"]

for fam in FAM:
    print(f"--- {fam}")
    for mach in MACH:
        row = {}
        for noz in NOZ:
            names = [f"Bambu {fam} @BBL {mach} {noz} nozzle",
                     f"Bambu {fam} @BBL {mach}"]
            for n in names:
                j = resolve(n)
                if j.get("filament_max_volumetric_speed"):
                    v = j["filament_max_volumetric_speed"]
                    row[noz] = v[0] if isinstance(v, list) else v
                    break
        print(f"    {mach:<5s} {row}")

print()
print("--- 现有 0.6 nozzle 的 filament 预设有哪些")
cnt = 0
for f in sorted(os.listdir(FIL)):
    if "0.6 nozzle" in f:
        print("   ", f[:-5])
        cnt += 1
        if cnt > 8:
            break
