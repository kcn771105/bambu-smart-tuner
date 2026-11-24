"""补齐官方 H2 系列机型（H2D / H2D Pro / H2S）。

真值来源
--------
`C:\Program Files\Bambu Studio\resources\profiles\BBL\machine\Bambu Lab H2D 0.4 nozzle.json`
等文件沿 `inherits` 链合并父级后读出的**官方出厂值**：

    H2D / H2D Pro : speed 1000 / acc_x 20000 / acc_z 500 / acc_travel 9000
                    jerk 9 (z=3) / nozzle_volume 130 / 层高 0.08~0.28
                    热床 350×320 mm / 最大高度 325 mm / 辅助风扇 1 / 腔温控制 1
    H2S           : speed 1000 / acc_x 20000 / acc_z 500 / acc_travel 9000
                    jerk 9 (z=3) / nozzle_volume 145 / 层高 0.08~0.28
                    热床 340×320 mm / 最大高度 340 mm / 辅助风扇 1 / 腔温控制 1

耗材体积流量上限（官方 filament 预设 `filament_max_volumetric_speed` 第 0 槽）：
    PLA 25 / PETG 13 / ABS 20 / ASA 20 / TPU 3.6（H2D、H2D Pro、H2S 三型一致）

用法
----
    python tools/_patch_add_h2_printers.py           # 只看会写什么
    python tools/_patch_add_h2_printers.py --apply    # 写回 rules/BambuRules.json
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

# 官方 machine 预设真值（0.4 喷嘴）。flow_by_printer 见模块 docstring。
H2_NODES = OrderedDict({
    "H2D": {
        "label": "Bambu Lab H2D",
        "group": "H2",
        "aliases": ["Bambu Lab H2D", "H2D"],
        "limits": OrderedDict([
            ("max_speed", 1000),
            ("max_accel", 20000),
            ("max_volumetric_speed", 25),
            ("min_layer_height_ratio", 0.2),
            ("max_layer_height_ratio", 0.7),
            ("max_travel_speed", 1000),
            ("max_travel_accel", 9000),
            ("max_jerk", 9),
            ("nozzle_volume", 130),
            ("min_layer_height", 0.08),
            ("max_layer_height", 0.28),
        ]),
        "baseline": OrderedDict([
            ("internal_solid_infill_acceleration", 12000),
            ("bridge_acceleration", 6000),
            ("top_surface_pattern", "monotonic"),
            ("bottom_surface_pattern", "monotonicline"),
        ]),
        "note": ("双喷头大尺寸机架（350×320×325 mm，芯温控制）：官方出厂速度 1000 mm/s、"
                 "加速度 20000、行程加速度 9000、体积流量 130 mm³；封闭腔体适合 ABS/ASA。"),
    },
    "H2DP": {
        "label": "Bambu Lab H2D Pro",
        "group": "H2",
        "aliases": ["Bambu Lab H2D Pro", "H2D Pro", "H2DP"],
        "limits": OrderedDict([
            ("max_speed", 1000),
            ("max_accel", 20000),
            ("max_volumetric_speed", 25),
            ("min_layer_height_ratio", 0.2),
            ("max_layer_height_ratio", 0.7),
            ("max_travel_speed", 1000),
            ("max_travel_accel", 9000),
            ("max_jerk", 9),
            ("nozzle_volume", 130),
            ("min_layer_height", 0.08),
            ("max_layer_height", 0.28),
        ]),
        "baseline": OrderedDict([
            ("internal_solid_infill_acceleration", 12000),
            ("bridge_acceleration", 6000),
            ("top_surface_pattern", "monotonic"),
            ("bottom_surface_pattern", "monotonicline"),
        ]),
        "note": "H2D 的专业版（同机架同运动学）：与 H2D 共用速度/加速度/流量上限，差异在喷头与耗材系统。",
    },
    "H2S": {
        "label": "Bambu Lab H2S",
        "group": "H2",
        "aliases": ["Bambu Lab H2S", "H2S"],
        "limits": OrderedDict([
            ("max_speed", 1000),
            ("max_accel", 20000),
            ("max_volumetric_speed", 25),
            ("min_layer_height_ratio", 0.2),
            ("max_layer_height_ratio", 0.7),
            ("max_travel_speed", 1000),
            ("max_travel_accel", 9000),
            ("max_jerk", 9),
            ("nozzle_volume", 145),
            ("min_layer_height", 0.08),
            ("max_layer_height", 0.28),
        ]),
        "baseline": OrderedDict([
            ("internal_solid_infill_acceleration", 12000),
            ("bridge_acceleration", 6000),
            ("top_surface_pattern", "monotonic"),
            ("bottom_surface_pattern", "monotonicline"),
        ]),
        "note": ("单喷头高流量版（340×320×340 mm）：热端体积流量 145 mm³ 为全系最高，"
                 "封腔 + 辅助风扇，ABS/ASA 大件首选。"),
    },
})

# 官方 filament 预设第 0 槽 max volumetric speed
FLOW = {"H2D": {"PLA": 25, "PETG": 13, "ASA": 20, "ABS": 20, "TPU": 3.6},
        "H2DP": {"PLA": 25, "PETG": 13, "ASA": 20, "ABS": 20, "TPU": 3.6},
        "H2S": {"PLA": 25, "PETG": 13, "ASA": 20, "ABS": 20, "TPU": 3.6}}


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"), object_pairs_hook=OrderedDict)

    added = [k for k in H2_NODES if k not in rules["printers"]]
    for k in added:
        rules["printers"][k] = H2_NODES[k]
    print("新增机型：", added or "（已存在，跳过）")
    print("机型总数：", len(rules["printers"]), "→", list(rules["printers"].keys()))

    updated = []
    for fk, fnode in rules["filaments"].items():
        fbp = fnode.setdefault("limits", {}).setdefault("flow_by_printer", {})
        for pk, table in FLOW.items():
            v = table.get(fk)
            if v is None:
                continue
            if fbp.get(pk) != v:
                fbp[pk] = v
                updated.append(f"{fk}×{pk}={v}")
        # 保持键顺序与 printers 一致，方便人读
        order = list(rules["printers"].keys())
        rules["filaments"][fk]["limits"]["flow_by_printer"] = OrderedDict(
            (k, fbp[k]) for k in order if k in fbp)
    print("耗材流量矩阵更新：", len(updated), "项 →", ", ".join(updated[:12]), "…" if len(updated) > 12 else "")

    # interactions / modes 里若用 when.printer 列举机型，把 H2 补进「大尺寸/封腔」相关规则
    print("交叉规则数：", len(rules.get("interactions", [])))

    if apply:
        bak = RULES.with_suffix(RULES.suffix + ".bak_h2")
        shutil.copy2(RULES, bak)
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print(f"已写回 {RULES}（备份 {bak.name}），{RULES.stat().st_size} bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
