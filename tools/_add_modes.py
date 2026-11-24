"""按官方过程预设生成三个新模式：快速草稿 / 精细 / 超精细。

沿用 tools/_rebuild_modes.py 的做法：
    · 连续量（速度 / 加速度 / 层高 / 角度）取「官方档 ÷ 官方标准档」的比值，
      写成 mul，作用在工程当前值上（不覆盖用户已经挑好的快慢）；
    · 结构性量（壳层数 / 渗透层数）走 STRUCTURAL 表，
      一律用 min（只增不减，绝不把用户已经调高的强度调低）；
    · 官方用「百分比 / 跟随 / 0=关闭」表达的键不参与换算。

官方对应关系：
    draft      ← 0.24mm Draft @BBL X1C        （层高放大、提速、支撑放宽）
    fine       ← 0.12mm Fine @BBL X1C         （层高压到 0.12、支撑收紧 20°）
    ultrafine  ← 0.08mm Extra Fine @BBL X1C   （层高压到 0.08、壳层加厚、支撑 15°）

用法：
    python tools/_add_modes.py            # dry-run，只打印
    python tools/_add_modes.py --apply    # 写回 rules/BambuRules.json
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import schema, scope                      # noqa: E402
from tools._dump_official_profiles import resolve    # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"

STD = "0.20mm Standard @BBL X1C"
DRAFT = "0.24mm Draft @BBL X1C"
FINE = "0.12mm Fine @BBL X1C"
ULTRA = "0.08mm Extra Fine @BBL X1C"

# 官方用「百分比 / 跟随 / 0=关闭 / 与机型强相关」表达的键，不做换算
SKIP = {
    "inner_wall_acceleration", "sparse_infill_acceleration",
    "small_perimeter_speed", "vertical_shell_speed",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
    "smooth_coefficient", "start_end_points",
    "seam_slope_type", "seam_slope_start_height", "seam_slope_gap",
    "seam_slope_min_length", "ironing_speed", "ironing_spacing", "ironing_inset",
    "bridge_flow", "seam_position",
    # 顶底壳厚度与线宽是「绝对几何量」，改了会直接破坏表面；
    # 官方按层高档位给，我们不跟着动（线宽由喷嘴缩放统一处理）。
    "top_shell_thickness", "bottom_shell_thickness",
    "line_width", "outer_wall_line_width", "inner_wall_line_width",
    "internal_solid_infill_line_width", "sparse_infill_line_width",
    "support_line_width", "initial_layer_line_width",
    "ironing_flow",
}

# 结构性量：强度下限用 min（只增不减）
STRUCTURAL: dict[str, dict[str, dict]] = {
    "draft": {
        # 官方 Draft 档顶底壳层降到 4 层；我们只保证不低于 4 层
        "top_shell_layers": {"min": 4},
        "top_color_penetration_layers": {"min": 4},
    },
    "fine": {
        # 官方 0.12mm Fine 档底壳 5 层、底部渗透 5 层
        "bottom_shell_layers": {"min": 5},
        "bottom_color_penetration_layers": {"min": 5},
    },
    "ultrafine": {
        # 官方 0.08mm Extra Fine 档顶底壳层 9 / 7 层、渗透 9 / 7 层
        "top_shell_layers": {"min": 9},
        "bottom_shell_layers": {"min": 7},
        "top_color_penetration_layers": {"min": 9},
        "bottom_color_penetration_layers": {"min": 7},
    },
}

# 官方档里「标准档是 0（关闭）、这一档打开了」的键：直接给绝对值
ABSOLUTE: dict[str, dict[str, dict]] = {
    "fine": {
        "overhang_1_4_speed": {"set": 60},
    },
    "ultrafine": {
        "overhang_1_4_speed": {"set": 60},
    },
}

META = {
    "draft": {
        "label": "快速草稿",
        "desc": "只求快出件：层高放到 0.24 mm、内壁与填充提速、支撑判定放宽。"
                "对应官方 0.24mm Draft 档。墙层与密度不额外加厚。",
    },
    "fine": {
        "label": "精细",
        "desc": "外观与层间结合优先：层高 0.12 mm、内壁与填充提速、"
                "悬垂面降速、支撑判定收紧到 20°。对应官方 0.12mm Fine 档。"
                "打印时间会明显变长。",
    },
    "ultrafine": {
        "label": "超精细",
        "desc": "外观拉满：层高 0.08 mm、顶底壳层加厚到 9/7 层、"
                "支撑判定收紧到 15°。对应官方 0.08mm Extra Fine 档，"
                "打印时间最长。",
    },
}


def num(v):
    """官方值 → 数字（数组取第 0 槽、百分比字符串去 %）。"""
    if isinstance(v, list):
        if not v:
            return None
        v = v[0]
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().rstrip("%")
        try:
            return float(t)
        except ValueError:
            return None
    return None


def build(std: dict, cur: dict, mode: str) -> dict:
    ops: dict = {}
    for k in sorted(set(std) | set(cur)):
        if k in SKIP or k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.PROCESS:
            continue
        kind = schema.PARAMS[k].kind
        if kind in (schema.ENUM, schema.BOOL):
            continue
        if kind in (schema.INT, schema.PCT, schema.PCT_NUM):
            continue                       # 结构性量走 STRUCTURAL 表
        a, b = num(std.get(k)), num(cur.get(k))
        if a is None or b is None:
            continue
        if abs(a - b) < 1e-9:
            continue
        if abs(a) < 1e-9:
            ops[k] = {"set": b}            # 标准档是 0（关闭）→ 给绝对值
        else:
            ratio = round(b / a, 4)
            if abs(ratio - 1.0) < 1e-9:
                continue
            ops[k] = {"mul": ratio}
    ops.update(STRUCTURAL.get(mode, {}))
    ops.update(ABSOLUTE.get(mode, {}))
    return ops


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))
    std = resolve(STD)
    plan = (("draft", DRAFT), ("fine", FINE), ("ultrafine", ULTRA))

    new_modes: dict[str, dict] = {}
    for mode, preset in plan:
        cur = resolve(preset)
        ops = build(std, cur, mode)
        new_modes[mode] = {"label": META[mode]["label"],
                           "desc": META[mode]["desc"],
                           "ops": ops}

    for mode, node in new_modes.items():
        old = (rules["modes"].get(mode) or {}).get("ops", {})
        print(f"=== {mode}（{node['label']}，{len(node['ops'])} 项）")
        for k, o in sorted(node["ops"].items()):
            mark = "" if old.get(k) == o else "   ← 变了"
            print(f"   {k}: {json.dumps(o, ensure_ascii=False)}{mark}")
        print()

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_modes2")
        shutil.copy2(RULES, bak)
        for mode, node in new_modes.items():
            rules["modes"][mode] = node
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
