"""把规则库里的 shape_profiles / support_policy / options.write_scopes 与代码同步。

用法：
    python tools/sync_rules.py            # 只看差异
    python tools/sync_rules.py --apply    # 写回 rules/BambuRules.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import modes as modes_reg  # noqa: E402
from core import schema, scope, shape_rules, support_plan  # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"


def build() -> dict:
    data = json.loads(RULES.read_text(encoding="utf-8"))

    # 1) 写入范围：默认只写切片工艺页
    opts = data.setdefault("options", {})
    opts["write_scopes"] = ["process"]
    opts.setdefault("scope_note", {
        "process": "切片工艺页：本程序唯一会写入的页面。",
        "filament": "耗材页：只读。其中的流量上限、标定值仍用来约束工艺参数。",
        "machine": "机器页：只读。其中的硬件上限、板面尺寸仍用来约束工艺参数。",
        "meta": "工程元数据：永不写入。",
    })

    # 2) 形状档：与 core/shape_rules.BUILTIN_PROFILES 保持一致
    data["shape_profiles"] = shape_rules.BUILTIN_PROFILES
    data["shape_profiles_meta"] = {
        "desc": "逐件形状原型 → 参数档。键是原型，值是 {模式: {参数键: 操作}}。",
        "merge_rule": {
            "min": "取所有对象里最小的（速度/加速度/层高/风扇/回抽）",
            "max": "取所有对象里最大的（墙层/壳层/密度/裙边）",
            "keep": "不参与合并（图案类/枚举类）",
        },
        "protos": [{"key": k, "label": l, "desc": d} for k, l, d in shape_rules.proto_table()],
        "modes": list(modes_reg.MODE_UI_ORDER),
        "howto": "新增形状原型：先在 core/shape_rules.py 的 PROTOS 里加一行，"
                 "再在这里加同名节点。改数值直接改本文件即可，不用改代码。",
    }

    # 3) 支撑策略阈值
    data["support_policy"] = support_plan.BUILTIN_POLICY
    data["support_policy_meta"] = {
        "desc": "支撑策略的判定阈值。支撑参数由模型几何（悬垂占比/高度/贴板情况）推出。",
        "howto": "改这里的阈值就能改变支撑触发与密度，不用改代码。",
        "keys": sorted(support_plan.BUILTIN_POLICY.keys()),
    }

    return data


def main() -> int:
    data = build()
    if "--apply" in sys.argv:
        RULES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写回 {RULES}（{RULES.stat().st_size} bytes）")
    else:
        print(json.dumps({
            "options": data["options"],
            "shape_profiles 原型数": len(data["shape_profiles"]),
            "support_policy 阈值数": len(data["support_policy"]),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
