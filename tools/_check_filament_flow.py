"""查询官方耗材预设解析后的热端流量上限（沿 inherits 链）。

用法：
    python tools/_check_filament_flow.py [预设名 ...]
"""
from __future__ import annotations

import json
import os
import sys

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\filament"


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
            for key, value in json.load(fh).items():
                if key not in ("inherits", "name", "description"):
                    out[key] = value
    return out


def main() -> int:
    names = sys.argv[1:] or [
        "Bambu PETG Basic @base",
        "Bambu PETG Basic @BBL X1C",
        "Bambu PETG Basic @BBL P1P",
        "Bambu PETG Basic @BBL P2S 0.4 nozzle",
        "Bambu PETG Basic @BBL A1",
        "Bambu PLA Basic @base",
        "Bambu PLA Basic @BBL P2S 0.4 nozzle",
        "Bambu ABS @base",
        "Bambu ASA @base",
        "Bambu TPU 95A @base",
    ]
    for name in names:
        data = resolve(name)
        print(f"{name:<44} max_vol={data.get('filament_max_volumetric_speed')} "
              f"ratio={data.get('filament_flow_ratio')} "
              f"fan={data.get('fan_min_speed')}/{data.get('fan_max_speed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
