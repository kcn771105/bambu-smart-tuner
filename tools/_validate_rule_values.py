"""校验规则库所有「set 类」操作的目标值是否合法（枚举在 choices 内、数值在区间内）。

用法：
    python tools/_validate_rule_values.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import schema  # noqa: E402


def check_set(key: str, value, where: str, bad: list[str]) -> None:
    spec = schema.PARAMS.get(key)
    if spec is None:
        bad.append(f"{where}: 键 {key} 不在参数表内")
        return
    if spec.kind in (schema.ENUM, schema.ENUM_ARRAY):
        if spec.choices and str(value) not in spec.choices:
            bad.append(f"{where}: {key} = {value!r} 不在枚举 {spec.choices} 内")
        return
    if spec.kind == schema.BOOL:
        if not isinstance(value, bool) and str(value) not in ("0", "1"):
            bad.append(f"{where}: {key} = {value!r} 不是布尔")
        return
    if spec.kind == schema.VEC_FLOAT:
        return
    try:
        num = float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        bad.append(f"{where}: {key} = {value!r} 不是数值")
        return
    if not (spec.vmin - 1e-9 <= num <= spec.vmax + 1e-9):
        bad.append(f"{where}: {key} = {value!r} 超出区间 {spec.vmin}~{spec.vmax}")


def main() -> int:
    with open(os.path.join(ROOT, "rules", "BambuRules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)

    bad: list[str] = []

    def walk(node: dict, where: str) -> None:
        for key, value in (node.get("set") or {}).items():
            check_set(key, value, where, bad)

    for mode, node in rules.get("modes", {}).items():
        walk(node, f"modes.{mode}")
        for fk, fnode in rules.get("filaments", {}).items():
            ops = ((fnode.get("mode_ops") or {}).get(mode) or {})
            for key, value in (ops.get("set") or {}).items():
                check_set(key, value, f"filaments.{fk}.mode_ops.{mode}", bad)
    for it in rules.get("interactions", []):
        walk(it, f"interaction[{it.get('id')}]")
    for pkey, pnode in rules.get("printers", {}).items():
        for key, value in (pnode.get("baseline") or {}).items():
            check_set(key, value, f"printers.{pkey}.baseline", bad)
    for fkey, fnode in rules.get("filaments", {}).items():
        for key, value in (fnode.get("baseline") or {}).items():
            check_set(key, value, f"filaments.{fkey}.baseline", bad)
    for proto, node in (rules.get("shape_profiles") or {}).items():
        ops = (node.get("ops") or {}) if isinstance(node, dict) else {}
        for key, value in (ops.get("set") or {}).items():
            check_set(key, value, f"shape_profiles.{proto}", bad)
    for key, value in (rules.get("defaults") or {}).items():
        check_set(key, value, "defaults", bad)

    print(f"规则库 set 类取值校验：{len(bad)} 处问题")
    for line in bad:
        print("  " + line)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
