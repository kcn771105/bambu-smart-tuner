"""从官方 machine 预设里沿 inherits 链解析出 H2 系列真值。

背景
----
`Bambu Lab H2D.json` 这类顶层文件只有 `inherits` 指向基座，
真正的 `machine_max_speed_x` / `nozzle_volume` / `bed_shape` 全在
`fdm_bbl_3dp_001_common.json` / `fdm_bbl_3dp_002_common.json` /
`fdm_machine_common.json` 里，必须递归合并父级才能拿到值。

用法：python tools/_dump_h2_machine.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

MACHINE_DIR = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL\machine")

TARGETS = [
    "Bambu Lab H2D",
    "Bambu Lab H2D Pro",
    "Bambu Lab H2S",
    "Bambu Lab P2S",
    "Bambu Lab X1 Carbon",
    "Bambu Lab A1",
]

KEYS = [
    "machine_max_speed_x", "machine_max_speed_y", "machine_max_speed_z",
    "machine_max_speed_e", "machine_max_acceleration_x",
    "machine_max_acceleration_y", "machine_max_acceleration_z",
    "machine_max_acceleration_e", "machine_max_acceleration_travel",
    "machine_max_acceleration_extruding", "machine_max_acceleration_retracting",
    "machine_max_jerk_x", "machine_max_jerk_y", "machine_max_jerk_z",
    "machine_max_jerk_e", "nozzle_volume", "printer_model",
    "printer_variant", "bed_shape", "max_layer_height", "min_layer_height",
    "max_print_height", "nozzle_diameter", "upward_compatible_machine",
    "auxiliary_fan", "support_chamber_temp_control", "chamber_temperatures",
]


def load(name: str) -> dict:
    p = MACHINE_DIR / (name + ".json")
    return json.load(io.open(p, encoding="utf-8-sig"))


def resolve(name: str, seen=None) -> dict:
    """递归合并 inherits 链（父级先写，子级后写覆盖）。"""
    seen = seen or set()
    if name in seen:
        return {}
    seen.add(name)
    try:
        raw = load(name)
    except FileNotFoundError:
        return {}
    parent = raw.pop("inherits", None)
    merged = {}
    if parent:
        merged.update(resolve(parent, seen))
    merged.update(raw)
    return merged


def main() -> int:
    for t in TARGETS:
        m = resolve(t)
        print("=" * 6, t)
        print("   inherits链顶层 ->", load(t).get("inherits"))
        for k in KEYS:
            if k in m:
                print(f"   {k} = {m[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
