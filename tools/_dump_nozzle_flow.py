"""把「喷嘴 → 熔池体积 / 流量上限」的官方真值拉出来（沿 inherits 链合并）。"""
import io
import json
import os
import re

MACH = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\machine"
FIL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\filament"


def load_raw(d, name):
    p = os.path.join(d, name + ".json")
    with io.open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def resolve(d, name, seen=None):
    seen = seen or set()
    if name in seen:
        return {}
    seen.add(name)
    try:
        raw = load_raw(d, name)
    except FileNotFoundError:
        return {}
    parent = raw.pop("inherits", None)
    out = {}
    if parent:
        out.update(resolve(d, parent, seen))
    out.update(raw)
    return out


print("=== machine: 各机型 × 各喷嘴 ===")
for f in sorted(os.listdir(MACH)):
    if not f.endswith(".json") or "nozzle" not in f:
        continue
    name = f[:-5]
    j = resolve(MACH, name)
    if j.get("type") != "machine":
        continue
    print(f"{name:<40s} nozzle={j.get('nozzle_diameter')} vol={j.get('nozzle_volume')} "
          f"variant={j.get('printer_variant')} type={j.get('nozzle_type')}")

print()
print("=== filament: 同一条料 × 各喷嘴（PETG / PLA，X1C）===")
for f in sorted(os.listdir(FIL)):
    if not f.endswith(".json"):
        continue
    if "PETG" not in f and "PLA" not in f:
        continue
    if "X1C" not in f:
        continue
    name = f[:-5]
    j = resolve(FIL, name)
    print(f"{name:<52s} flow={j.get('filament_max_volumetric_speed')}")
