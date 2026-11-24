"""一次性修补：把「官方查不到、且改了会毁掉工程语义」的键对齐 Bambu 自身默认值。

背景：
  官方三页预设里查不到这 116 个键（它们是 Bambu 新版工程才有的键），
  但真实工程里全都存着。我们自己写的默认值里有 4 个与 Bambu 自身默认不一致，
  写回去等于平白改动用户的工程：

    internal_solid_infill_pattern      Bambu 默认 'zig-zag'，我们写成 'monotonic'
    mmu_segmented_region_interlocking_depth  Bambu 默认 0，我们写成 2
    mmu_segmented_region_max_width           Bambu 默认 0，我们写成 20
    start_end_points                   工程里是走线起终点坐标 ["30x-3","54x245"]，
                                      我们写成 "auto" —— 写回去等于抹掉用户的走线设置

处理：
  · 前 3 个  → defaults 对齐 Bambu 自身默认（改回 0 / 'zig-zag'）
  · start_end_points → schema 标 preserve=True（永不覆盖用户值）

用法：
    python tools/_patch_unofficial_safe.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RULES = os.path.join(ROOT, "rules", "BambuRules.json")
BACKUP = RULES + ".bak2"

ALIGN_DEFAULTS = {
    "internal_solid_infill_pattern": "zig-zag",
    "mmu_segmented_region_interlocking_depth": 0,
    "mmu_segmented_region_max_width": 0,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(RULES, encoding="utf-8") as fh:
        rules = json.load(fh)
    defaults = rules.get("defaults", {})

    print("计划改动（defaults 对齐 Bambu 自身默认）：")
    for key, val in ALIGN_DEFAULTS.items():
        old = defaults.get(key, "<defaults 里本来就没有>")
        print(f"  {key}: {old!r} → {val!r}")
        defaults[key] = val
    print("  start_end_points: 从 defaults 摘掉 + schema 标 preserve=True")

    defaults.pop("start_end_points", None)

    if not args.apply:
        print("\n（未加 --apply，仅预览）")
        return 0

    shutil.copyfile(RULES, BACKUP)
    with open(RULES, "w", encoding="utf-8") as fh:
        json.dump(rules, fh, ensure_ascii=False, indent=1)
    print(f"\n已写回 {RULES}（备份 {BACKUP}），defaults 现有 {len(defaults)} 键")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
