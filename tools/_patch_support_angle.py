"""把支撑判定角改成「按官方档位给绝对值」，并把交叉规则里的判定角让给模式层。

背景
----
官方过程预设对「悬垂判定角」有明确取值：
    Standard 30° / Strength 30° / High Quality 25° / Fine 20° / Extra Fine 15° / Draft 35°
之前这条角是由交叉规则 support-default-off（quality 族，40°）绝对写死的，
结果精细档（官方 20°）被交叉规则顶回 40°。

本脚本做三件事：
    1. 交叉规则 support-default-off / support-strength 里删掉 support_threshold_angle，
       判定角改由「模式层 + 支撑层」负责。
    2. 模式 ops 里给 support_threshold_angle 官方绝对值：
         quality 25 / strength ≤30（max 语义，不动用户更敏感的角）/ draft 35 / fine 20 / ultrafine 15
    3. 打印对照表。

用法：python tools/_patch_support_angle.py [--apply]
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

# 模式 → 官方档位的判定角（度）
OFFICIAL_ANGLE = {
    "balanced": None,        # 标准档 30° = 工程默认值，不动
    "quality": {"set": 25},  # High Quality 档
    "strength": {"max": 30}, # Strength 档：不超过 30°（用户设更小的角就保留）
    "draft": {"set": 35},    # Draft 档
    "fine": {"set": 20},     # Fine 档
    "ultrafine": {"set": 15},# Extra Fine 档
}

DROP_FROM_INTERACTIONS = {
    "support-default-off",
    "support-strength",
}


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))

    # ---- 1）交叉规则：删掉判定角
    for it in rules.get("interactions", []):
        if it.get("id") in DROP_FROM_INTERACTIONS:
            it.get("set", {}).pop("support_threshold_angle", None)

    # ---- 2）模式 ops：写官方绝对值
    for mode, op in OFFICIAL_ANGLE.items():
        mnode = rules["modes"].get(mode)
        if not mnode:
            continue
        ops = mnode.setdefault("ops", {})
        ops.pop("support_threshold_angle", None)
        if op is not None:
            ops["support_threshold_angle"] = dict(op)

    print("模式判定角：")
    for mode in ("balanced", "strength", "quality", "draft", "fine", "ultrafine"):
        mnode = rules["modes"].get(mode, {})
        print(f"   {mode:10s} {mnode.get('label',''):8s} "
              f"{json.dumps((mnode.get('ops') or {}).get('support_threshold_angle'), ensure_ascii=False)}")

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_angle")
        shutil.copy2(RULES, bak)
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
