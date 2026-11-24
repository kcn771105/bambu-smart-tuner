"""统计「切片工艺页」参数被哪几层规则覆盖，用来回答「所有能调的都有吗」。

覆盖层：
    defaults        通用基准（官方 process 预设解析结果）
    printers        机型基线
    filaments       耗材基线（相对操作）
    modes           模式档（官方三档预设换算）
    interactions    交叉规则（耗材×机型等）
    geometry        几何驱动层（core/geom_rules.py）
    shape           逐件形状层（shape_profiles）
    support         支撑决策层（support_plan）

用法：python tools/_coverage_process.py [--csv PATH]
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import geom_rules, schema, scope, support_plan  # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"


def collect() -> tuple[dict, list[str]]:
    rules = json.load(io.open(RULES, encoding="utf-8"))
    hits: dict[str, list[str]] = {}
    proc_keys = [k for k in schema.PARAMS if scope.scope_of(k) == scope.PROCESS]

    def mark(key: str, layer: str) -> None:
        if key in schema.PARAMS and scope.scope_of(key) == scope.PROCESS:
            hits.setdefault(key, []).append(layer)

    for k in rules.get("defaults", {}):
        mark(k, "defaults")
    for pname, pnode in rules.get("printers", {}).items():
        for k in pnode.get("baseline", {}):
            mark(k, "printers")
    for fname, fnode in rules.get("filaments", {}).items():
        for k in fnode.get("baseline", {}):
            mark(k, "filaments")
        for mnode in fnode.get("mode_ops", {}).values():
            for k in mnode:
                mark(k, "filaments")
    for mname, mnode in rules.get("modes", {}).items():
        for k in mnode.get("ops", {}):
            mark(k, "modes")
    for it in rules.get("interactions", []):
        for k in it.get("set", {}):
            mark(k, "interactions")
        for k in it.get("ops", {}):
            mark(k, "interactions")
    for r in geom_rules.RULES:
        mark(r.key, "geometry")
    for pkey, modes in rules.get("shape_profiles", {}).items():
        for mnode in modes.values():
            for k in mnode:
                mark(k, "shape")
    for k in support_plan.SUPPORT_PREFIXES:
        pass
    # 支撑层：decision 里可能产出的键
    for k in ("enable_support", "support_type", "support_style",
              "support_base_pattern_spacing", "support_threshold_angle",
              "support_interface_spacing", "support_interface_top_layers",
              "support_top_z_distance", "support_bottom_z_distance",
              "support_object_xy_distance", "support_critical_regions_only",
              "support_remove_small_overhang", "support_on_build_plate_only",
              "tree_support_branch_angle", "tree_support_branch_diameter",
              "tree_support_wall_count"):
        mark(k, "support")
    return hits, proc_keys


def main() -> int:
    hits, proc_keys = collect()
    layers = ["defaults", "printers", "filaments", "modes", "interactions",
              "geometry", "shape", "support"]
    print(f"切片工艺页参数总数：{len(proc_keys)}")
    for L in layers:
        n = sum(1 for k in proc_keys if L in hits.get(k, []))
        print(f"  被 {L:13s} 触及：{n:3d}  ({n*100.0/len(proc_keys):.1f}%)")
    touched = [k for k in proc_keys if k in hits]
    print(f"\n至少被一层触及：{len(touched)} / {len(proc_keys)} "
          f"({len(touched)*100.0/len(proc_keys):.1f}%)")
    untouched = [k for k in proc_keys if k not in hits]
    print(f"未被任何规则触及（只能保留工程原值）：{len(untouched)}")
    for k in untouched:
        s = schema.PARAMS[k]
        print(f"   {k:42s} {s.group_label}｜{s.label}")
    if "--csv" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--csv") + 1])
        with io.open(out, "w", encoding="utf-8", newline="") as f:
            f.write("key,label,group,layers\n")
            for k in proc_keys:
                s = schema.PARAMS[k]
                f.write(f'"{k}","{s.label}","{s.group_label}","{";".join(hits.get(k, []))}"\n')
        print(f"\n已写 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
