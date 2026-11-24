"""修正规则库里的「耗材 × 机型」官方流量上限表（flow_by_printer）。

之前用机型组（X1/P1/P2/A1）近似，导致 PETG@P2S 取到了 @base 的 8 mm³/s，
而官方 P2S 标定是 13 —— 速度被无谓地压低一半。

本脚本按官方实测矩阵逐机型写入：
    PLA  X1C/X1/X1E/P1S/P1P/P2S/P2P/A1/A1mini = 21
    PETG X1C/X1/X1E/P2S/P2P = 13，A1/A1mini = 9，P1S/P1P = 8（官方无专属标定，取 @base）
    ABS  X1C/X1/X1E/P2S/P2P/A1/A1mini/P1S/P1P = 16
    ASA  同上 = 18
    TPU  全部 = 3.6（官方 Bambu TPU 95A 实测）

用法：
    python tools/_patch_flow_matrix.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, "rules", "BambuRules.json")
BACKUP = RULES + ".bak4"

PRINTERS = ["X1C", "X1", "X1E", "P1S", "P1P", "P2S", "P2P", "A1", "A1mini", "GENERIC"]

FLOW = {
    "PLA":    {p: 21.0 for p in PRINTERS},
    "PETG":   {**{p: 13.0 for p in ("X1C", "X1", "X1E", "P2S", "P2P")},
               **{p: 9.0 for p in ("A1", "A1mini")},
               **{p: 8.0 for p in ("P1S", "P1P", "GENERIC")}},
    "ABS":    {p: 16.0 for p in PRINTERS},
    "ASA":    {p: 18.0 for p in PRINTERS},
    "TPU":    {p: 3.6 for p in PRINTERS},
    "GENERIC": {p: 8.0 for p in PRINTERS},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(RULES, encoding="utf-8") as fh:
        rules = json.load(fh)

    for fkey, table in FLOW.items():
        node = rules["filaments"].get(fkey)
        if node is None:
            print(f"  跳过未登记耗材 {fkey}")
            continue
        limits = node.setdefault("limits", {})
        old = limits.get("flow_by_printer", {})
        limits["flow_by_printer"] = table
        print(f"{fkey}: flow_by_printer 更新（旧 {len(old)} 项 → 新 {len(table)} 项）")
        for p in PRINTERS:
            if old.get(p) != table[p]:
                print(f"    {p:<9} {old.get(p, '<无>')} → {table[p]}")

    if not args.apply:
        print("\n（未加 --apply，仅预览）")
        return 0

    shutil.copyfile(RULES, BACKUP)
    with open(RULES, "w", encoding="utf-8") as fh:
        json.dump(rules, fh, ensure_ascii=False, indent=1)
    print(f"\n已写回 {RULES}（备份 {BACKUP}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
