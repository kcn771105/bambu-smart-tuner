"""用官方三个过程预设重建模式策略（modes.*.ops）。

官方预设对应：
    balanced ← 0.20mm Standard @BBL X1C      （官方标准档）
    strength ← 0.20mm Strength @BBL X1C      （官方强度档）
    quality  ← 0.16mm High Quality @BBL X1C  （官方质量档）

做法
----
1. 连续量（速度、加速度）：算「官方档位 ÷ 官方标准档」的比值，写成 mul，
   作用在「工程当前值」这个基准上 —— 用户原本挑的快慢不会被一把压到官方值，
   只是按官方比例往那个方向调。
2. 结构性量（墙层数、壳层数、密度）：这类参数本身就是「模式定义」
   （强度档官方墙 6 圈 / 密度 25%，质量档顶底各 6 层），
   官方是绝对值定义，比例换算没有意义 → 写成 min / set。
   强度档一律用 min（只增不减，绝不把用户已经更高的强度调低）。
3. 枚举（填充图案、顶面图案）：直接取官方档的值。
4. 官方用「百分比 / 跟随 / 0=关闭」表达的键不参与换算（它们的含义不是绝对值）。

用法：python tools/_rebuild_modes.py [--apply]
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import schema, scope                     # noqa: E402
from tools._dump_official_profiles import resolve  # noqa: E402

RULES = ROOT / "rules" / "BambuRules.json"

STD = "0.20mm Standard @BBL X1C"
STR = "0.20mm Strength @BBL X1C"
HQ = "0.16mm High Quality @BBL X1C"

# 官方用「百分比 / 跟随 / 0=关闭 / 机器相关」语义表达的键，不做换算
SKIP = {
    "inner_wall_acceleration", "sparse_infill_acceleration",
    "small_perimeter_speed", "vertical_shell_speed",
    "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
    "smooth_coefficient", "start_end_points",
    "seam_slope_type", "seam_slope_start_height", "seam_slope_gap",
    "seam_slope_min_length", "ironing_speed", "ironing_spacing", "ironing_inset",
    "ironing_flow", "seam_position", "bridge_flow", "top_shell_thickness",
    "bottom_shell_thickness",
}

# 结构性量（整数 / 百分比）→ 按官方档的绝对值给，但强度档用 min（只增不减）
STRUCTURAL: dict[str, dict[str, dict]] = {
    "strength": {
        # 官方 0.20mm Strength：wall_loops 6、sparse_infill_density 25%
        "wall_loops": {"min": 6},
        "sparse_infill_density": {"min": 25},
        "skeleton_infill_density": {"min": 25},
        "skin_infill_density": {"min": 25},
        "top_shell_layers": {"min": 5},
        # 用户规格：强度优先要加大填充重叠（官方强度档是 15%）
        "infill_wall_overlap": {"set": 20},
    },
    "balanced": {
        # 官方标准档就是通用基准；均衡模式在它之上做折中：
        # 墙层 3（官方标准 2 / 强度 6 之间）、密度 ~20%（15%→25% 之间）、
        # gyroid 填充（各向同性、强度更均匀）、重叠 18%、外壁降一档保层间粘合。
        "wall_loops": {"set": 3},
        "sparse_infill_density": {"mul": 1.35},
        "sparse_infill_pattern": {"set": "gyroid"},
        "infill_wall_overlap": {"set": 18},
        "outer_wall_speed": {"mul": 0.85},
        "outer_wall_acceleration": {"mul": 0.8},
        "top_surface_speed": {"mul": 0.9},
        # 加减速分离：X1C 以上机型官方推荐，减少拐角处的鼓包
        "accel_to_decel_enable": {"set": True},
    },
    "quality": {
        # 官方 0.16mm High Quality：顶底各 6/4 层、密度 15%、gyroid
        "top_shell_layers": {"min": 6},
        "bottom_shell_layers": {"min": 4},
        "sparse_infill_pattern": {"set": "gyroid"},
        "top_surface_pattern": {"set": "monotonic"},
        # 用户规格：表面质量优先要抑制层纹，接缝间隙收到 12%
        "seam_gap": {"set": 12},
        # 支撑间隙跟着层高缩（官方 HQ 档 0.16mm → 间隙 0.16mm）
        "support_top_z_distance": {"mul": 0.8},
        "support_bottom_z_distance": {"mul": 0.8},
        # 悬垂判定角收一档（官方 HQ 档 25°，标准档 30°）
        "support_threshold_angle": {"mul": 0.8333},
    },
}

# 枚举键：直接取官方档的值
ENUMS: dict[str, dict[str, dict]] = {
    "balanced": {"top_surface_pattern": {"set": "monotonic"}},
    "strength": {"sparse_infill_pattern": {"set": "grid"}},
    "quality": {"sparse_infill_pattern": {"set": "gyroid"},
                "top_surface_pattern": {"set": "monotonic"}},
}


def num(v):
    """把官方值转成数字（数组取第 0 槽、百分比字符串转数值）。"""
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
    """官方档位相对标准档的差异 → 相对操作。"""
    ops: dict = {}
    for k in sorted(set(std) | set(cur)):
        if k in SKIP or k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.PROCESS:
            continue
        kind = schema.PARAMS[k].kind
        if kind in (schema.ENUM, schema.BOOL):
            continue                      # 枚举走 ENUMS 表
        if kind in (schema.INT, schema.PCT, schema.PCT_NUM):
            continue                      # 结构性量走 STRUCTURAL 表
        a, b = num(std.get(k)), num(cur.get(k))
        if a is None or b is None:
            continue
        if abs(a - b) < 1e-9:
            continue
        if abs(a) < 1e-9:
            ops[k] = {"set": b}            # 标准档是 0（关闭）→ 直接给绝对值
        else:
            ops[k] = {"mul": round(b / a, 4)}
    ops.update(STRUCTURAL.get(mode, {}))
    ops.update(ENUMS.get(mode, {}))
    return ops


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8"))
    std = resolve(STD)
    new_modes: dict[str, dict] = {}
    for mode, preset in (("balanced", STD), ("strength", STR), ("quality", HQ)):
        cur = resolve(preset)
        new_modes[mode] = build(std, cur, mode)

    for mode, ops in new_modes.items():
        old = rules["modes"][mode].get("ops", {})
        print(f"=== {mode}（{len(ops)} 项）")
        for k, o in sorted(ops.items()):
            mark = "" if old.get(k) == o else "   ← 变了"
            print(f"   {k}: {json.dumps(o, ensure_ascii=False)}{mark}")

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_modes")
        shutil.copy2(RULES, bak)
        for mode, ops in new_modes.items():
            rules["modes"][mode]["ops"] = ops
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
