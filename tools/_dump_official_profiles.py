"""对比官方 process 预设与 0.20mm Standard @BBL X1C 的差异（用于重建模式档 / 扩展模式）。

沿 inherits 链解析官方预设，父级先写、子级后写。
用法：python tools/_dump_official_profiles.py [预设名片段...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL\process")

REF = "0.20mm Standard @BBL X1C"


def resolve(name: str) -> dict:
    """沿 inherits 链合并；父级先写、子级后写覆盖。"""
    chain: list[dict] = []
    cur = name
    seen: set[str] = set()
    while cur:
        if cur in seen:
            break
        seen.add(cur)
        p = PROC / (cur if cur.endswith(".json") else cur + ".json")
        if not p.exists():
            break
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        chain.append(data)
        cur = data.get("inherits") or ""
    out: dict = {}
    for data in reversed(chain):
        for k, v in data.items():
            if k == "inherits":
                continue
            out[k] = v
    return out


def norm(v):
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, str):
        s = v.strip()
        if s.endswith("%"):
            try:
                return float(s[:-1])
            except ValueError:
                return s
        try:
            return float(s)
        except ValueError:
            return s
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def main() -> int:
    names = sys.argv[1:] or [
        "0.20mm Balanced Strength @BBL X1C",
        "0.16mm Balanced Quality @BBL X1C",
        "0.12mm Balanced Quality @BBL X1C",
        "0.24mm Balanced Quality @BBL X1C",
        "0.32mm Balanced Quality @BBL X1C",
        "0.20mm High Quality @BBL X1C",
        "0.20mm Strength @BBL X1C",
        "0.16mm Optimal @BBL X1C",
        "0.12mm Fine @BBL X1C",
        "0.12mm Draft @BBL X1C",
        "0.24mm Draft @BBL X1C",
        "0.14mm Extra Draft @BBL X1C",
    ]
    ref = resolve(REF)
    for name in names:
        if not (PROC / (name + ".json")).exists():
            print(f"### {name}  —— 预设不存在")
            continue
        cur = resolve(name)
        diffs = []
        for k in sorted(set(ref) | set(cur)):
            if k == "inherits":
                continue
            a, b = norm(ref.get(k)), norm(cur.get(k))
            if a != b:
                diffs.append((k, ref.get(k), cur.get(k)))
        print(f"### {name}   差异 {len(diffs)} 项")
        for k, a, b in diffs:
            print(f"   {k:38s} {a!r} -> {b!r}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
