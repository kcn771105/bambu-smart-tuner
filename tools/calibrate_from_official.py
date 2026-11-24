"""用本机 Bambu Studio 官方预设校准 rules/BambuRules.json 的基准层。

数据来源（只读，不修改官方文件）：
  C:\\Program Files\\Bambu Studio\\resources\\profiles\\BBL\\
      process\\fdm_process_single_common.json   → 通用工艺基线
      process\\fdm_process_single_0.20.json     → 0.20mm 档位覆盖
      process\\0.20mm Standard @BBL <机型>.json  → 各机型官方速度/加速度

校准规则：
  1. defaults 层 ← 官方通用基线（common 叠加 0.20mm 档）
  2. 各机型 baseline 层 ← 该机型官方预设中「与通用基线不同」的项
  3. schema 里标了 preserve 的键（用户实测标定值 / 跟随语义 / 盘面摆位）一律跳过
  4. 值的形态按 schema 类型还原：array_pct 保持 "50%"、bool 保持 true/false、
     enum 保持字符串、int/float 保持数值

用法：
  python tools/calibrate_from_official.py            # 只报告差异
  python tools/calibrate_from_official.py --apply    # 写回 rules/BambuRules.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import schema  # noqa: E402

BBL = pathlib.Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")
RULES = ROOT / "rules" / "BambuRules.json"


# ------------------------------------------------------------------ 预设读取

def find_preset(name: str) -> pathlib.Path | None:
    """按 stem 在 machine/filament/process 三个目录里找同名 json。"""
    for sub in ("machine", "filament", "process"):
        for p in (BBL / sub).glob("*.json"):
            if p.stem == name:
                return p
    return None


def resolve_preset(name: str) -> dict:
    """沿 inherits 链合并出最终生效值（链上同名键后者覆盖前者）。"""
    path = find_preset(name)
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    parent = data.get("inherits")
    out = resolve_preset(parent) if parent else {}
    out.update({k: v for k, v in data.items() if k != "inherits"})
    return out


# ------------------------------------------------------------------ 形态还原

def typed_value(key: str, raw):
    """把官方原始值还原成 Bambu 工程里的原生形态。"""
    spec = schema.spec(key)
    if spec is None:
        return None
    kind = spec.kind
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip()

    if kind in (schema.PCT, schema.PCT_NUM, schema.ARRAY_PCT):
        if text.endswith("%"):
            return text
        try:
            return f"{float(text)}%"
        except ValueError:
            return text
    if kind == schema.BOOL:
        if text in ("1", "true", "True"):
            return True
        if text in ("0", "false", "False"):
            return False
        return text
    if kind == schema.ENUM:
        return text
    if kind == schema.ENUM_ARRAY:
        return text
    if kind == schema.INT:
        try:
            return int(round(float(text)))
        except ValueError:
            return text
    if kind == schema.FLOAT:
        try:
            return float(text)
        except ValueError:
            return text
    if kind == schema.ARRAY_FLOAT:
        try:
            return float(text)
        except ValueError:
            return text
    return text


# ------------------------------------------------------------------ 官方基线

def official_common() -> dict:
    """通用工艺基线（所有机型共用的那一层）。"""
    return resolve_preset("fdm_process_single_common")


def official_020() -> dict:
    """0.20mm 档位在通用基线之上的覆盖。"""
    return resolve_preset("fdm_process_single_0.20")


# 各机型的官方 0.20mm Standard 预设名
MACHINE_PRESETS = {
    "X1C": "0.20mm Standard @BBL X1C",
    "X1": "0.20mm Standard @BBL X1C",   # X1/X1E 与 X1C 同机架
    "X1E": "0.20mm Standard @BBL X1C",
    "P1S": "0.20mm Standard @BBL P1P",
    "P1P": "0.20mm Standard @BBL P1P",
    "P2S": "0.20mm Standard @BBL P2S",
    "P2P": "0.20mm Standard @BBL P2S",
    "A1": "0.20mm Standard @BBL A1",
    "A1mini": "0.20mm Standard @BBL A1M",
}

# 只搬这些键（速度/加速度/壳层/密度/支撑这类核心工艺键）
TAKE_KEYS = [
    "default_acceleration", "outer_wall_acceleration", "top_surface_acceleration",
    "travel_acceleration", "initial_layer_acceleration", "initial_layer_travel_acceleration",
    "outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "travel_speed",
    "support_speed", "bridge_speed", "initial_layer_speed", "initial_layer_infill_speed",
    "gap_infill_speed", "overhang_1_4_speed", "overhang_2_4_speed",
    "overhang_3_4_speed", "overhang_4_4_speed", "overhang_totally_speed",
    "top_shell_layers", "bottom_shell_layers", "sparse_infill_density",
    "layer_height", "line_width", "outer_wall_line_width", "inner_wall_line_width",
    "sparse_infill_line_width", "internal_solid_infill_line_width",
    "top_surface_line_width", "initial_layer_line_width", "support_line_width",
    "sparse_infill_pattern", "top_surface_pattern", "bottom_surface_pattern",
    "support_type", "support_style", "support_base_pattern",
    "support_base_pattern_spacing", "support_interface_spacing",
    "support_threshold_angle", "support_top_z_distance", "support_bottom_z_distance",
    "support_object_xy_distance", "support_interface_top_layers",
    "support_interface_bottom_layers", "support_expansion",
    "elefant_foot_compensation", "infill_wall_overlap", "bridge_flow",
    "smooth_coefficient", "initial_layer_print_height", "prime_tower_width",
    "spiral_mode", "wall_generator", "reduce_crossing_wall",
    "seam_position", "seam_placement_away_from_overhangs", "only_one_wall_top",
    "detect_overhang_wall", "detect_thin_wall", "enable_support",
    "bridge_no_support", "interface_shells", "symmetric_infill_y_axis",
    "z_direction_outwall_speed_continuous", "avoid_crossing_wall_includes_support",
    "enable_height_slowdown", "slowdown_start_height", "slowdown_end_height",
    "slowdown_start_speed", "slowdown_end_speed", "small_perimeter_threshold",
    "small_perimeter_speed", "vertical_shell_speed",
    "enable_arc_fitting", "enable_circle_compensation", "prime_tower_flat_ironing",
    "prime_tower_enable_framework", "wipe_tower_no_sparse_layers",
    "override_filament_scarf_seam_setting", "detect_floating_vertical_shell",
    "support_on_build_plate_only", "support_interface_loop_pattern",
    "minimum_sparse_infill_area", "infill_direction", "resolution",
    "enable_overhang_speed", "enable_prime_tower", "support_interface_speed",
    "pre_start_fan_time", "slowdown_start_acc", "slowdown_end_acc",
    "slow_down_min_speed", "fan_cooling_layer_time", "slow_down_layer_time",
]


def build_layers() -> tuple[dict, dict]:
    """返回 (defaults 覆盖, 各机型 baseline 覆盖)。"""
    common = official_common()
    p020 = official_020()

    # 通用层：先 common，再用 0.20mm 档覆盖（官方主力档位）
    defaults: dict = {}
    for src in (common, p020):
        for k in TAKE_KEYS:
            if k in src:
                v = typed_value(k, src[k])
                if v is not None:
                    defaults[k] = v

    # 机型层：只取「与通用层不同」的项
    common_flat = {k: typed_value(k, v) for k, v in {**common, **p020}.items() if k in TAKE_KEYS}
    per_machine: dict = {}
    for mkey, pname in MACHINE_PRESETS.items():
        src = official_machine(pname)
        node: dict = {}
        for k in TAKE_KEYS:
            if k not in src:
                continue
            v = typed_value(k, src[k])
            if v is None:
                continue
            if common_flat.get(k) == v:
                continue          # 与通用层相同 → 不重复写
            node[k] = v
        per_machine[mkey] = node
    return defaults, per_machine


def official_machine(name: str) -> dict:
    """某机型的官方 Standard 过程预设。"""
    return resolve_preset(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写回 rules/BambuRules.json")
    args = ap.parse_args()

    if not BBL.exists():
        print(f"找不到官方预设目录：{BBL}")
        return 1

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    defaults, per_machine = build_layers()

    def skipped(key: str) -> bool:
        spec = schema.spec(key)
        return bool(spec and spec.preserve)

    print("=== 通用 defaults 层 ===")
    cur = rules["defaults"]
    n_diff = 0
    for k, v in defaults.items():
        if skipped(k):
            print(f"  = {k}: 保留用户标定值（官方 {v} 不采纳）")
            continue
        old = cur.get(k)
        if old is None:
            print(f"  + {k}: {old} → {v}")
            n_diff += 1
        elif old != v and str(old) != str(v):
            print(f"  ~ {k}: {old} → {v}")
            n_diff += 1
    print(f"defaults 实际改动 {n_diff} 处 / 官方层 {len(defaults)} 键")

    print()
    for mkey, node in per_machine.items():
        pnode = rules["printers"].get(mkey)
        if not pnode:
            continue
        base = pnode.get("baseline", {})
        diffs = [(k, base.get(k), v) for k, v in node.items()
                 if not skipped(k) and (base.get(k) != v and str(base.get(k)) != str(v))]
        print(f"=== {mkey} baseline 差异 {len(diffs)} 处 ===")
        for k, old, v in diffs:
            print(f"  ~ {k}: {old} → {v}")

    if not args.apply:
        print("\n（加 --apply 才会写回规则库）")
        return 0

    merged = dict(cur)
    for k, v in defaults.items():
        if skipped(k):
            continue
        merged[k] = v
    rules["defaults"] = merged

    for mkey, node in per_machine.items():
        pnode = rules["printers"].get(mkey)
        if not pnode:
            continue
        base = dict(pnode.get("baseline", {}))
        for k, v in node.items():
            if skipped(k):
                continue
            base[k] = v
        pnode["baseline"] = base

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写回 {RULES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
