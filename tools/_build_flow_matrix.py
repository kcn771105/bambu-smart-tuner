"""从官方 filament 预设自动生成「耗材 × 机型」热端流量上限矩阵。

官方 Bambu Studio 给每个「耗材 × 机型」单独标过热端流量上限（同一个 PETG，
X1C 是 13 mm³/s、A1 只有 9 mm³/s、TPU 只有 3.6），这个值直接决定速度能被压到多少。

本脚本沿 inherits 链解析官方预设，抽出每个组合的
filament_max_volumetric_speed 与 filament_flow_ratio，并写进规则库的
filaments[*].limits.flow_by_printer / flow_ratio。

用法：
    python tools/_build_flow_matrix.py            # 只打印矩阵
    python tools/_build_flow_matrix.py --apply    # 写进规则库
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL\filament"
RULES = os.path.join(ROOT, "rules", "BambuRules.json")
BACKUP = RULES + ".bak5"

# 规则库里的机型键 → 官方预设名里的机型标识
PRINTER_TOKENS = {
    "X1C": "X1C", "X1": "X1", "X1E": "X1E",
    "P1S": "P1S", "P1P": "P1P",
    "P2S": "P2S", "P2P": "P2P",
    "A1": "A1", "A1mini": "A1M",
    "GENERIC": "",
}

# 规则库耗材键 → 官方预设名里的材料词（按优先级排列）
MATERIAL_TOKENS = {
    "PLA": ["PLA"],
    "PETG": ["PETG"],
    "ASA": ["ASA"],
    "ABS": ["ABS"],
    "TPU": ["TPU 95A", "TPU 85A", "TPU"],
}


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


def first_num(raw):
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


def build_matrix() -> tuple[dict, dict]:
    """返回 ({耗材: {机型: 流量}}, {耗材: 流量比})。"""
    names = [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BBL, "*.json"))]
    flow: dict[str, dict[str, float]] = {}
    ratio: dict[str, float] = {}

    for fkey, tokens in MATERIAL_TOKENS.items():
        flow[fkey] = {}
        for pkey, ptok in PRINTER_TOKENS.items():
            best = None
            for name in names:
                if not name.startswith("Bambu "):
                    continue
                if not any(tok in name.upper() for tok in tokens):
                    continue
                if ptok and not re.search(r"@BBL\s+" + re.escape(ptok) + r"\b", name):
                    continue
                if not ptok and "@BBL" in name:
                    continue
                best = name
                break
            if best is None:
                continue
            data = resolve(best)
            value = first_num(data.get("filament_max_volumetric_speed"))
            if value:
                flow[fkey][pkey] = value
                r = first_num(data.get("filament_flow_ratio"))
                if r:
                    ratio.setdefault(fkey, r)
    return flow, ratio


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    flow, ratio = build_matrix()
    print("官方「耗材 × 机型」热端流量上限（mm³/s）：")
    for fkey, table in flow.items():
        row = "  ".join(f"{p}={v:g}" for p, v in sorted(table.items()))
        print(f"  {fkey:<8} {row}")
    print("\n流量比：", {k: round(v, 3) for k, v in ratio.items()})

    if not args.apply:
        print("\n（未加 --apply，仅预览）")
        return 0

    with open(RULES, encoding="utf-8") as fh:
        rules = json.load(fh)
    for fkey, node in rules.get("filaments", {}).items():
        table = flow.get(fkey)
        if not table:
            print(f"  跳过 {fkey}：官方没找到对应预设")
            continue
        limits = node.setdefault("limits", {})
        old = limits.get("flow_by_printer", {})
        limits["flow_by_printer"] = table
        if fkey in ratio:
            limits["flow_ratio"] = ratio[fkey]
        print(f"\n{fkey}:")
        for p in sorted(set(old) | set(table)):
            if old.get(p) != table.get(p):
                print(f"    {p:<9} {old.get(p, '<无>')} → {table.get(p, '<无>')}")

    shutil.copyfile(RULES, BACKUP)
    with open(RULES, "w", encoding="utf-8") as fh:
        json.dump(rules, fh, ensure_ascii=False, indent=1)
    print(f"\n已写回 {RULES}（备份 {BACKUP}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
