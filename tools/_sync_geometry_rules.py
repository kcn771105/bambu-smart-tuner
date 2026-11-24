"""把 core/geom_rules.py 的内置几何规则同步进规则库（geometry_rules 节点）。

同步后用户在 rules/BambuRules.json 的 geometry_rules 节点里就能直接改
「什么几何特征 → 调哪个参数 → 调成多少」，不用改主程序代码。

用法：
    python tools/_sync_geometry_rules.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import geom_rules  # noqa: E402

RULES = os.path.join(ROOT, "rules", "BambuRules.json")
BACKUP = RULES + ".bak3"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(RULES, encoding="utf-8") as fh:
        rules = json.load(fh)

    table = geom_rules.to_json_rules()
    rules["geometry_rules"] = table
    rules["geometry_rules_meta"] = {
        "desc": "几何驱动细调表：按模型几何事实（细高比/扁平度/壁厚/悬垂占比/高度/体积…）"
                "调整切片工艺页参数。cond 是几何条件名，op 是动作（set/mul/min/max/add），"
                "priority 越小越先应用，priority>=99 是「跟随模式档」的占位规则。",
        "conds": geom_rules.COND_DESC,
        "howto": [
            "1. cond 只能取 conds 里列出的条件名。",
            "2. op 支持 set（直接设值）/ mul（乘）/ min（下限）/ max（上限）/ add（加）。",
            "3. modes 留空 = 三种模式都生效；填 ['quality'] = 只在表面质量优先生效。",
            "4. 想让某条规则不生效，把它的 priority 改成 999 或删掉整条。",
            "5. 改完保存，重新打开软件即可生效（规则库在启动时读取）。",
        ],
    }

    print(f"geometry_rules 节点：{len(table)} 条规则")
    if not args.apply:
        print("（未加 --apply，仅预览）")
        return 0

    shutil.copyfile(RULES, BACKUP)
    with open(RULES, "w", encoding="utf-8") as fh:
        json.dump(rules, fh, ensure_ascii=False, indent=1)
    size = os.path.getsize(RULES)
    print(f"已写回 {RULES}（备份 {BACKUP}），文件 {size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
