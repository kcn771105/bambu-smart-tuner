"""调参预算与「空走速度」修正补丁。

三件事
------
1. 给每个模式加 `time_budget_pct`：引擎在调用方没指定时长上限时，
   自动按模式自带的预算执行回调（超出就按代价最小的顺序回退）。
   不设预算的模式写 null = 不回调（fine / ultrafine 靠小层高换质量，
   把它拉回时间等于毁掉这一档）。

2. `petg-stringing` 里的 `travel_speed: 250` 是错的。空走速度对拉丝
   是**越快越好**（慢空走 = 喷嘴在移动途中持续出料）。折回 250 只会让
   一个 1000 mm/s 的平台白白慢 4 倍，拉丝一点没少。改为不写绝对值，
   只留一条提示，真正的防拉丝靠耗材页的回抽/擦嘴/Z hop（只读不改）。

3. 模式预算写进 JSON，用户可以直接编辑。

用法：
    python tools/_patch_time_budget.py            # dry-run
    python tools/_patch_time_budget.py --apply
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

# 模式时长预算（%）。参照官方档位相对 0.20mm Standard 的真实差距：
#   Draft 更快、Standard 基准、Strength 慢一截、HQ 慢一倍多、
#   Fine / Extra Fine 层高成倍变小，时间本来就要几倍，不设上限。
BUDGET = OrderedDict([
    ("strength", 200),
    ("quality", 170),
    ("balanced", 40),
    ("draft", 10),
    ("fine", None),
    ("ultrafine", None),
])

BUDGET_DESC = {
    "strength": "强度档允许明显变慢（加墙、加密度），但不超过 200%",
    "quality": "质量档允许变慢一倍多，超过就退回部分填充/速度",
    "balanced": "均衡档硬约束：最多慢 40%",
    "draft": "草稿档是「快」的档，最多慢 10%",
    "fine": "精细档不设时长上限（靠小层高换质量）",
    "ultrafine": "超精细档不设时长上限",
}


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"), object_pairs_hook=OrderedDict)

    for mk, node in rules["modes"].items():
        if mk in BUDGET:
            node["time_budget_pct"] = BUDGET[mk]
            node["time_budget_note"] = BUDGET_DESC[mk]
            print(f"modes.{mk}.time_budget_pct = {BUDGET[mk]}")

    changed = []
    for it in rules["interactions"]:
        if it.get("id") == "petg-stringing":
            st = it.get("set") or {}
            if "travel_speed" in st:
                st.pop("travel_speed")
                changed.append("删除 petg-stringing.set.travel_speed（慢空走只会加剧拉丝）")
            it["set"] = st
            it["warn"] = ("PETG 易拉丝：空走速度保持机型高速（慢空走会让喷嘴在途中持续出料，"
                          "越慢越拉丝）；真正治拉丝的是耗材页的回抽长度/速度、擦嘴、Z hop——"
                          "那几项属于耗材页，只读不改，需要你在 Bambu Studio 耗材设置里确认。"
                          "工艺页这边把斜切关闭（斜切会挂料）。")
    print("\n".join(changed) or "petg-stringing 无需修改")

    # 模式节点顺序：把 time_budget_pct 放在 desc 之后
    for mk, node in rules["modes"].items():
        if "time_budget_pct" not in node:
            continue
        ordered = OrderedDict()
        for k, v in node.items():
            if k in ("time_budget_pct", "time_budget_note"):
                continue
            ordered[k] = v
        ordered["time_budget_pct"] = node["time_budget_pct"]
        ordered["time_budget_note"] = node.get("time_budget_note", "")
        rules["modes"][mk] = ordered

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_budget")
        shutil.copy2(RULES, bak)
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
