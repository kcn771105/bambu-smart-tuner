"""草稿档去掉「加厚类」结构项。

背景
----
官方 `0.24mm Draft @BBL X1C` 的顶底壳层是 **降到** 4 层（标准档 5 层）。
我们引擎里 min 语义是「下限」——写成 {"min": 4} 实际效果是
「用户若已调到 3 层，拉回 4 层」，对草稿档来说反而是加厚，
与「草稿档只求快、不加厚」的定位冲突。

处理：从 draft.ops 里去掉 top_shell_layers / top_color_penetration_layers。
官方草稿档这两项是往下调，我们不做向下调整（宁可保持用户的壳层厚度），
层高放大后顶面绝对厚度略增，属于保守方向。

用法：python tools/_patch_draft_no_thicken.py [--apply]
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

DROP = ("top_shell_layers", "top_color_penetration_layers",
        "bottom_shell_layers", "bottom_color_penetration_layers",
        "wall_loops", "sparse_infill_density", "infill_wall_overlap")


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))
    ops = rules["modes"]["draft"].setdefault("ops", {})
    dropped = [k for k in DROP if k in ops]
    for k in dropped:
        ops.pop(k)
    print("草稿档移除的加厚类项：", dropped or "（无）")
    print("草稿档剩余 ops：", json.dumps(ops, ensure_ascii=False))

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_draft")
        shutil.copy2(RULES, bak)
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
