"""对比六档模式在真实工程上的关键参数落值（排查模式扩展是否按预期）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, rules_engine, threemf   # noqa: E402

PROJ = Path(sys.argv[1] if len(sys.argv) > 1
            else r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")

KEYS = [
    "layer_height", "wall_loops", "top_shell_layers", "bottom_shell_layers",
    "sparse_infill_density", "sparse_infill_pattern",
    "outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
    "top_surface_speed", "travel_speed", "default_acceleration",
    "support_threshold_angle", "support_base_pattern_spacing",
    "support_interface_spacing", "support_top_z_distance",
    "overhang_1_4_speed", "infill_wall_overlap",
]


def main() -> int:
    eng = rules_engine.build_engine()
    proj = threemf.ThreeMfProject.load(PROJ)
    det = detector.detect(proj, eng.rules)
    hw = hardware.read(proj)
    prof = model_analysis.analyse(proj)
    print(f"工程：{PROJ.name}｜机型 {det.printer_key}｜耗材 {det.filament_key}"
          f"｜喷嘴 {det.nozzle}｜对象 {prof.object_count}")
    print("原始值：")
    orig = {}
    for k in KEYS:
        if k in proj.settings:
            orig[k] = proj.settings[k]
    for k in KEYS:
        if k in orig:
            print(f"   {k:34s} {orig[k]}")

    print()
    print(f"{'参数':34s} {'balanced':>14s} {'draft':>14s} {'fine':>14s} {'ultrafine':>14s}")
    cols = {}
    for m in ("balanced", "draft", "fine", "ultrafine"):
        res = eng.optimize(proj.settings,
                           printer_key=det.printer_key,
                           filament_key=det.filament_key,
                           nozzle=det.nozzle,
                           mode_key=m,
                           model_profile=prof,
                           hardware_info=hw,
                           time_cap_pct=None)
        vals = dict(res.write_values)
        cols[m] = vals
    for k in KEYS:
        row = []
        for m in ("balanced", "draft", "fine", "ultrafine"):
            v = cols[m].get(k)
            if v is None:
                row.append("-")
            elif isinstance(v, list):
                row.append(str(v[0]))
            else:
                row.append(f"{v:g}" if isinstance(v, (int, float)) else str(v))
        print(f"{k:34s} {row[0]:>14s} {row[1]:>14s} {row[2]:>14s} {row[3]:>14s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
