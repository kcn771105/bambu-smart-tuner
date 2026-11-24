"""一次性脚本：按官方 machine 预设真值校准 printers[*].limits。

官方真值来源（沿 inherits 链解析 Bambu Studio 的 machine/ 预设，
0.4 喷嘴档）：
    X1/X1C/X1E/P1P/P1S : speed 500, acc_x 20000, acc_travel 9000, jerk 9, 层高 0.08~0.28, nozzle_volume 107
    P2S               : speed 600, acc_x 20000, acc_travel 10000, 层高 0.08~0.28, nozzle_volume 110
    A1                : speed 500, acc_x 12000, acc_travel 9000, 层高 0.08~0.28, nozzle_volume 92
    A1 mini           : speed 500, acc_x 20000, acc_travel 9000, 层高 0.08~0.28, nozzle_volume 92

层高绝对窗口随喷嘴线性变：nozzle×0.2 ~ nozzle×0.7
（0.2→0.04~0.14，0.4→0.08~0.28，0.6→0.12~0.42，0.8→0.16~0.56）

旧值错在：A1/A1mini 的 max_speed 写成 250（官方 500）、P1 写 400（官方 500）、
A1 的 max_accel 写 6000（官方 12000）、A1mini 写 5000（官方 20000），
而且没有层高绝对区间（只有比例 ratio）。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

RULES = Path(__file__).resolve().parent.parent / "rules" / "BambuRules.json"

# 官方 0.4 喷嘴档真值
OFFICIAL = {
    "X1":  dict(max_speed=500, max_accel=20000, max_travel_speed=500, max_travel_accel=9000, jerk=9, volume=107),
    "P1":  dict(max_speed=500, max_accel=20000, max_travel_speed=500, max_travel_accel=9000, jerk=9, volume=107),
    "P2":  dict(max_speed=600, max_accel=20000, max_travel_speed=600, max_travel_accel=10000, jerk=9, volume=110),
    "A1":  dict(max_speed=500, max_accel=12000, max_travel_speed=500, max_travel_accel=9000, jerk=9, volume=92),
}

# 组 → 机型键
GROUPS = {"X1": ["X1C", "X1", "X1E"],
          "P1": ["P1S", "P1P"],
          "P2": ["P2S", "P2P"],
          "A1": ["A1", "A1mini"],
          "GENERIC": ["GENERIC"]}

# 通用兜底（不认识机型时用最保守的）
GENERIC = dict(max_speed=300, max_accel=8000, max_travel_speed=500,
                max_travel_accel=8000, jerk=9, volume=92)


def main() -> None:
    raw = io.open(RULES, encoding="utf-8").read()
    rules = json.loads(raw)

    changed = []
    for group, keys in GROUPS.items():
        truth = OFFICIAL.get(group, GENERIC)
        for key in keys:
            node = rules["printers"].get(key)
            if node is None:
                print("缺机型节点:", key)
                continue
            lim = node.setdefault("limits", {})
            before = dict(lim)
            lim["max_speed"] = truth["max_speed"]
            lim["max_accel"] = truth["max_accel"]
            lim["max_travel_speed"] = truth["max_travel_speed"]
            lim["max_travel_accel"] = truth["max_travel_accel"]
            lim["max_jerk"] = truth["jerk"]
            lim["nozzle_volume"] = truth["volume"]
            # 层高绝对区间（0.4 喷嘴档）+ 比例（供其它喷嘴等比推算）
            lim["min_layer_height"] = 0.08
            lim["max_layer_height"] = 0.28
            lim["min_layer_height_ratio"] = 0.2
            lim["max_layer_height_ratio"] = 0.7
            if before != lim:
                changed.append(key)

    io.open(RULES, "w", encoding="utf-8").write(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
    print("已校准机型:", changed)


if __name__ == "__main__":
    main()
