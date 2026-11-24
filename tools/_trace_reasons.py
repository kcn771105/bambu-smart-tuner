"""打印某些参数在引擎里的完整推导链（每层的原因）。

用法：
    python tools/_trace_reasons.py [工程路径] [键1 键2 ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, rules_engine, threemf  # noqa: E402

DEFAULT = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
KEYS = ["outer_wall_speed", "inner_wall_speed", "travel_speed", "sparse_infill_speed",
        "top_surface_speed", "enable_prime_tower", "top_one_wall_type",
        "pre_start_fan_time", "brim_width", "skirt_loops"]


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    keys = sys.argv[2:] or KEYS
    eng = rules_engine.build_engine()
    proj = threemf.ThreeMfProject.load(src)
    orig = dict(proj.settings)
    hw = hardware.read(proj)
    prof = model_analysis.analyse(proj)
    det = detector.detect(proj, eng.rules)
    res = eng.optimize(orig, printer_key=det.printer_key,
                       filament_key=det.filament_key,
                       nozzle=hw.nozzle_diameter or det.nozzle or 0.4,
                       mode_key="balanced", model_profile=prof, hardware_info=hw)
    for key in keys:
        row = next((r for r in res.rows if r.key == key), None)
        if row is None:
            print(f"\n{key}: 不在 rows 里")
            continue
        print(f"\n=== {key} ===")
        print(f"  原值 {row.old_raw!r} → 新值 {row.new_raw!r}  写入={row.will_write}")
        for part in row.reason.split(" → "):
            print("   ·", part)
    return 0


if __name__ == "__main__":
    sys.exit(main())
