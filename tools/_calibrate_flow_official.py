"""一次性脚本：按官方实测矩阵修正 filaments[*].limits.flow_by_printer。

旧值的问题：把「耗材通用基线」当成了「逐机型标定」，导致
    PETG 在 P2S 上取到 8（通用 @base 值），而不是官方为 P2S 标的 13；
    PETG 在 X1C 上也取到 8（应为 13）。
8 mm³/s 是 Bambu 给所有机器的通用兜底值，不是某台机器的能力上限，
用它去钳速度会把速度压到 95 mm/s（真实能跑 200+），时长凭空 +288%。

官方实测矩阵（沿 inherits 链解析官方 filament 预设，单位 mm³/s）：
    PLA  : X1C/X1/P2S/A1/A1M = 21（H2D/H2S = 25），ratio 0.98
    PETG : X1C/X1/P2S = 13，A1/A1M = 9（ratio 0.94），P1 系列无专属标定 → 8
    ABS  : X1C/X1E/P2S/A1 = 16，ratio 0.95
    ASA  : X1C/X1E/P2S/A1 = 18，ratio 0.95
    TPU  : X1C/X1/P2S/A1/A1M = 3.6（@base 写的 15 是通用上限，真实只能跑 3~4）
"""
from __future__ import annotations

import io
import json
from pathlib import Path

RULES = Path(__file__).resolve().parent.parent / "rules" / "BambuRules.json"

FLOW_BY_PRINTER = {
    "PLA": {
        "X1C": 21, "X1": 21, "X1E": 21,
        "P1S": 21, "P1P": 21,
        "P2S": 21, "P2P": 21,
        "A1": 21, "A1mini": 21,
        "GENERIC": 21,
    },
    "PETG": {
        "X1C": 13, "X1": 13, "X1E": 13,
        "P1S": 8, "P1P": 8,          # P1 系列官方没有 PETG 专属标定
        "P2S": 13, "P2P": 13,
        "A1": 9, "A1mini": 9,
        "GENERIC": 8,
    },
    "ABS": {
        "X1C": 16, "X1": 16, "X1E": 16,
        "P1S": 16, "P1P": 16,
        "P2S": 16, "P2P": 16,
        "A1": 16, "A1mini": 16,
        "GENERIC": 16,
    },
    "ASA": {
        "X1C": 18, "X1": 18, "X1E": 18,
        "P1S": 18, "P1P": 18,
        "P2S": 18, "P2P": 18,
        "A1": 18, "A1mini": 18,
        "GENERIC": 18,
    },
    "TPU": {
        "X1C": 3.6, "X1": 3.6, "X1E": 3.6,
        "P1S": 3.6, "P1P": 3.6,
        "P2S": 3.6, "P2P": 3.6,
        "A1": 3.6, "A1mini": 3.6,
        "GENERIC": 3.6,
    },
    "GENERIC": {
        "X1C": 8, "X1": 8, "X1E": 8,
        "P1S": 8, "P1P": 8,
        "P2S": 8, "P2P": 8,
        "A1": 8, "A1mini": 8,
        "GENERIC": 8,
    },
}

RATIO = {"PLA": 0.98, "PETG": 0.95, "ABS": 0.95, "ASA": 0.95, "TPU": 1.0,
         "GENERIC": 0.95}


def main() -> None:
    rules = json.loads(io.open(RULES, encoding="utf-8").read())
    changed = []
    for fkey, node in rules.get("filaments", {}).items():
        lim = node.setdefault("limits", {})
        table = FLOW_BY_PRINTER.get(fkey) or FLOW_BY_PRINTER["GENERIC"]
        before = dict(lim)
        lim["flow_by_printer"] = dict(table)
        lim["flow_ratio"] = RATIO.get(fkey, 0.95)
        # 通用上限取该耗材所有机型里的最小值（保守兜底）
        lim["max_volumetric_speed"] = min(table.values())
        if before != lim:
            changed.append(fkey)
    io.open(RULES, "w", encoding="utf-8").write(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
    print("已修正耗材流量矩阵:", changed)


if __name__ == "__main__":
    main()
