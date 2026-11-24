"""检查「按模型细调」覆盖了哪些工艺页参数，哪些还没被模型层触及。

用法：python tools/audit_shape_coverage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import scope, shape_rules, support_plan, schema   # noqa: E402


def main() -> int:
    eng = None
    try:
        import json
        rules = json.loads((ROOT / "rules" / "BambuRules.json").read_text(encoding="utf-8"))
    except Exception:
        rules = {}

    shape_keys: set[str] = set()
    for proto, modes in (rules.get("shape_profiles") or shape_rules.BUILTIN_PROFILES).items():
        for mode, ops in modes.items():
            shape_keys |= set(ops.keys())

    support_keys: set[str] = set()
    for key, val in (rules.get("support_policy") or support_plan.BUILTIN_POLICY).items():
        support_keys.add(key)

    proc = [k for k in schema.PARAMS if scope.scope_of(k) == scope.PROCESS]
    touched = shape_keys | support_keys

    print(f"工艺页参数共 {len(proc)} 项")
    print(f"形状层触及 {len(shape_keys & set(proc))} 项；支撑策略触及 "
          f"{len(support_keys & set(proc))} 项（阈值表，不是直接写键）")

    by_group: dict[str, list[str]] = {}
    for k in proc:
        by_group.setdefault(schema.PARAMS[k].group, []).append(k)

    print("\n按分组统计（总数 / 被模型层触及）：")
    for g, keys in by_group.items():
        n = len([k for k in keys if k in touched])
        flag = "  ← 有缺口" if n < len(keys) else ""
        label = schema.PARAMS[keys[0]].group_label
        print(f"  {label:<10} {len(keys):>3} / {n:>3}{flag}")

    print("\n未被模型层触及的工艺页参数：")
    miss = [k for k in proc if k not in touched]
    for k in miss:
        s = schema.PARAMS[k]
        print(f"  {s.group:<10} {s.label:<18} {k}")
    print(f"合计 {len(miss)} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
