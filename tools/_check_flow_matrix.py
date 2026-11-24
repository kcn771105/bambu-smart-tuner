"""临时工具：按「耗材族 × 机型」解析官方热端流量上限（沿 inherits 链取最终值）。"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.calibrate_official_v3 import resolve_preset, BBL  # noqa: E402

FAM_PRESETS = {
    "PLA": ["Bambu PLA Basic @base", "Bambu PLA Basic @BBL {m}", "Bambu PLA Basic @BBL {m} 0.4 nozzle"],
    "PETG": ["Bambu PETG Basic @base", "Bambu PETG Basic @BBL {m}", "Bambu PETG Basic @BBL {m} 0.4 nozzle"],
    "ABS": ["Bambu ABS @base", "Bambu ABS @BBL {m}", "Bambu ABS @BBL {m} 0.4 nozzle"],
    "ASA": ["Bambu ASA @base", "Bambu ASA @BBL {m}", "Bambu ASA @BBL {m} 0.4 nozzle"],
    "TPU": ["Bambu TPU 95A @base", "Bambu TPU 95A @BBL {m}", "Bambu TPU 95A @BBL {m} 0.4 nozzle"],
}
MACHINES = ["X1C", "X1", "X1E", "P1P", "P1S", "P2S", "P2P", "A1", "A1M", "H2D", "H2S"]


def n1(v):
    if isinstance(v, list):
        v = v[0] if v else None
    try:
        return float(str(v).rstrip("%"))
    except Exception:
        return None


def flow_of(name):
    src = resolve_preset(name)
    return n1(src.get("filament_max_volumetric_speed")), n1(src.get("filament_flow_ratio"))


print("== 官方 @base（0.4 喷嘴通用）流量上限 ==")
for fam, names in FAM_PRESETS.items():
    print(f"  {fam:5s} base -> flow={flow_of(names[0])}")

print("\n== 官方按机型（取第一个存在的非 0.2 nozzle 预设） ==")
for fam, names in FAM_PRESETS.items():
    for m in MACHINES:
        hit = None
        for tmpl in names[1:]:
            nm = tmpl.format(m=m)
            if (BBL / "filament" / f"{nm}.json").exists():
                hit = nm
                break
        if hit:
            print(f"  {fam:5s} {m:5s} -> flow={flow_of(hit)}   ({hit})")
        else:
            print(f"  {fam:5s} {m:5s} -> <无专属预设>")
