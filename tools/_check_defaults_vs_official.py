"""比对 rules/BambuRules.json 的 defaults 与官方参照预设解析结果。

用法：
    python tools/_check_defaults_vs_official.py [--full]

输出：
  · 我们有、官方没有（官方基线查不到）的键
  · 双方都有但数值/形态不同的键
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import schema  # noqa: E402

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
PROCESS = os.path.join(BBL, "process")
REFERENCE = "0.20mm Standard @BBL X1C"


def resolve(stem: str, folder: str) -> dict:
    """沿 inherits 链解析官方预设（父级先、子级后，子级覆盖父级）。"""
    chain: list[str] = []
    seen = set()
    cur = stem
    while cur and cur not in seen:
        seen.add(cur)
        path = os.path.join(folder, cur + ".json")
        if not os.path.exists(path):
            break
        chain.append(cur)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        cur = data.get("inherits")
    out: dict = {}
    for name in reversed(chain):           # 父级先写，子级后写（子级覆盖父级）
        path = os.path.join(folder, name + ".json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for key, value in data.items():
            if key in ("inherits", "name", "description"):
                continue
            out[key] = value
    return out


def norm(value) -> str:
    if isinstance(value, list):
        return json.dumps(value[:1], ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="打印全部差异")
    args = ap.parse_args()

    rules_path = os.path.join(ROOT, "rules", "BambuRules.json")
    with open(rules_path, encoding="utf-8") as fh:
        rules = json.load(fh)
    ours = rules.get("defaults", {})

    official = resolve(REFERENCE, PROCESS)

    only_ours = [k for k in sorted(ours) if k not in official]
    differing = []
    for key in sorted(ours):
        if key not in official:
            continue
        if norm(ours[key]) != norm(official[key]):
            differing.append((key, official[key], ours[key]))

    print(f"官方参照预设：{REFERENCE}")
    print(f"官方解析键数：{len(official)}")
    print(f"我们 defaults 键数：{len(ours)}")
    print(f"官方查不到（我们独有）：{len(only_ours)}")
    print(f"双方都有但值/形态不同：{len(differing)}")
    for key in only_ours:
        print(f"  [仅我们] {key} = {ours[key]!r}")
    for key, off, our in differing:
        print(f"  [值不同] {key}: 官方={off!r} 我们={our!r}")

    unknown = [k for k in only_ours if k in schema.PARAMS]
    print(f"\n上述键中在 schema 内登记的：{len(unknown)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
