"""打印官方 machine 预设里的硬件上限（供规则库 printers[*].limits 对齐）。

用法：python tools/_dump_machine_limits.py
"""
from __future__ import annotations

import glob
import json
import os
import re

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\machine"

KEYS = ["machine_max_speed_x", "machine_max_speed_y",
        "machine_max_acceleration_x", "machine_max_acceleration_y",
        "machine_max_acceleration_travel",
        "machine_max_jerk_x", "machine_max_jerk_y",
        "machine_max_speed_z", "machine_max_acceleration_z",
        "min_layer_height", "max_layer_height",
        "nozzle_volume", "nozzle_diameter",
        "printable_area"]


def resolve(stem: str) -> dict:
    chain, seen, cur = [], set(), stem
    while cur and cur not in seen:
        seen.add(cur)
        path = os.path.join(BBL, cur + ".json")
        if not os.path.exists(path):
            break
        chain.append(cur)
        with open(path, encoding="utf-8") as fh:
            cur = json.load(fh).get("inherits")
    out: dict = {}
    for name in reversed(chain):
        with open(os.path.join(BBL, name + ".json"), encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                if k not in ("inherits", "name", "description"):
                    out[k] = v
    return out


def first_num(raw):
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


def main() -> int:
    names = [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BBL, "*.json"))]
    for name in sorted(names):
        data = resolve(name)
        row = {k: first_num(data.get(k)) for k in KEYS if k != "printable_area"}
        if not any(row.values()):
            continue
        print(f"\n=== {name} ===")
        for k, v in row.items():
            if v is not None:
                print(f"   {k:<34} {v:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
