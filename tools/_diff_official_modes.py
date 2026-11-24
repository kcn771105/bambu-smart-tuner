"""对比官方三个过程预设，输出模式之间的差异（只列工艺页键）。

官方预设对应关系：
    balanced ← 0.20mm Standard @BBL X1C      （官方标准档）
    strength ← 0.20mm Strength @BBL X1C      （官方强度档）
    quality  ← 0.16mm High Quality @BBL X1C  （官方质量档）
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import schema, scope                     # noqa: E402
from tools._dump_official_profiles import resolve  # noqa: E402

STD = "0.20mm Standard @BBL X1C"
STR = "0.20mm Strength @BBL X1C"
HQ = "0.16mm High Quality @BBL X1C"

# 这些键官方用「百分比 / 跟随」语义表达，不能当绝对值比较
SKIP = {
    "inner_wall_acceleration", "sparse_infill_acceleration",
    "small_perimeter_speed", "vertical_shell_speed",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
    "smooth_coefficient", "start_end_points",
}


def show(name: str, ref: dict, cur: dict) -> None:
    print(f"\n=== {name} vs Standard ===")
    for k in sorted(set(ref) | set(cur)):
        if k in SKIP or k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.PROCESS:
            continue
        a, b = ref.get(k), cur.get(k)
        if a == b:
            continue
        print(f"  {k}: {json.dumps(a, ensure_ascii=False)} → {json.dumps(b, ensure_ascii=False)}"
              f"   [{schema.PARAMS[k].kind}]")


def main() -> int:
    std, st, hq = resolve(STD), resolve(STR), resolve(HQ)
    show("Strength", std, st)
    show("HighQuality", std, hq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
