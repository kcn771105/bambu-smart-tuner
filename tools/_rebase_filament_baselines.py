"""把耗材基线从「自造绝对值」改成「相对用户当前值的温和修正」。

背景（实测结论）：
- 官方 Bambu Studio 的 filament 预设里**没有**任何速度类键
  （outer_wall_speed / inner_wall_speed / sparse_infill_speed / top_surface_speed
  全部属于 process 页，即切片工艺页）。
- 我们此前在 filaments[*].baseline 里写的绝对速度（PETG 160/220/220/160 等）
  是自造的保守值，会把用户在工程里挑好的速度直接覆盖掉，
  再经模式层 → 形状层 → 几何层 → 流量钳制逐层相乘，
  导致外壁速度从 200 被压到 104（-48%），完全偏离官方基线。

改法：
- 耗材差异一律写成**相对操作**（mul / add / min / max），
  作用在「工程当前值」这个基准上，只做温和修正。
- TPU 保留硬上限（用 max 表示上限，如 {"max": 50}），
  因为柔性材料必须低速慢打，这是硬约束不是偏好。
- 删掉官方不存在的键（support_density / gap_fill_speed）。

用法：python tools/_rebase_filament_baselines.py [--apply]
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

# 每个耗材的「相对修正」表。
# 语义：mul=按比例微调；add=加一点；min=下限（抬高）；max=上限（压低）。
NEW_BASELINE: dict[str, dict] = {
    # PLA：官方没有耗材级速度差异；层间粘性好、翘曲风险低，完全保持用户设置。
    "PLA": {},
    # PETG：官方 process 基线与 PLA 相同；只因拉丝风险轻微降一档速度。
    "PETG": {
        "outer_wall_speed": {"mul": 0.95},
        "inner_wall_speed": {"mul": 0.95},
        "sparse_infill_speed": {"mul": 0.95},
        "internal_solid_infill_speed": {"mul": 0.95},
        "top_surface_speed": {"mul": 0.95},
        "support_top_z_distance": {"add": 0.05},
        "support_object_xy_distance": {"add": 0.05},
    },
    # ASA：收缩偏大、层间粘合一般，轻微降速换取稳定。
    "ASA": {
        "outer_wall_speed": {"mul": 0.95},
        "inner_wall_speed": {"mul": 0.95},
        "sparse_infill_speed": {"mul": 0.95},
        "internal_solid_infill_speed": {"mul": 0.95},
        "top_surface_speed": {"mul": 0.95},
        "support_top_z_distance": {"add": 0.05},
    },
    # ABS：需要保温、收缩量大，速度轻微下调。
    "ABS": {
        "outer_wall_speed": {"mul": 0.95},
        "inner_wall_speed": {"mul": 0.95},
        "sparse_infill_speed": {"mul": 0.95},
        "internal_solid_infill_speed": {"mul": 0.95},
        "top_surface_speed": {"mul": 0.95},
        "support_top_z_distance": {"add": 0.05},
    },
    # TPU：柔性材料必须低速慢打 —— 这里用「上限」表达硬约束。
    "TPU": {
        "outer_wall_speed": {"max": 50},
        "inner_wall_speed": {"max": 60},
        "sparse_infill_speed": {"max": 60},
        "internal_solid_infill_speed": {"max": 60},
        "top_surface_speed": {"max": 40},
        "initial_layer_speed": {"max": 25},
        "initial_layer_infill_speed": {"max": 30},
        "travel_speed": {"max": 150},
        "support_speed": {"max": 40},
        "bridge_speed": {"max": 15},
        "overhang_2_4_speed": {"max": 20},
        "overhang_3_4_speed": {"max": 12},
        "overhang_4_4_speed": {"max": 8},
        # TPU 容易粘支撑 → 支撑底纹放疏一点（间距越大越疏）
        "support_base_pattern_spacing": {"min": 3.0},
        "support_top_z_distance": {"add": 0.05},
    },
    "GENERIC": {},
}


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8"))
    changed = []
    for fkey, node in (rules.get("filaments") or {}).items():
        if fkey not in NEW_BASELINE:
            continue
        old = node.get("baseline") or {}
        new = NEW_BASELINE[fkey]
        if old != new:
            changed.append(f"{fkey}: {json.dumps(old, ensure_ascii=False)} "
                           f"→ {json.dumps(new, ensure_ascii=False)}")
            node["baseline"] = new
    # TPU 强度优先的密度 30% 对柔性材料偏激进，收一点
    tpu_modes = ((rules.get("filaments") or {}).get("TPU") or {}).get("mode_ops") or {}
    if "strength" in tpu_modes:
        old = json.dumps(tpu_modes["strength"], ensure_ascii=False)
        new = {"wall_loops": {"set": 4}, "sparse_infill_density": {"set": 25}}
        if old != json.dumps(new, ensure_ascii=False):
            changed.append(f"TPU.mode_ops.strength: {old} → {json.dumps(new, ensure_ascii=False)}")
            tpu_modes["strength"] = new

    for line in changed:
        print("· " + line)
    if not changed:
        print("无改动。")
        return 0
    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_filament")
        shutil.copy2(RULES, bak)
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
