"""出一份「只声明差异、不改档名」的验证文件 —— 用来证明 different_settings_to_system 生效。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import (detector, hardware, model_analysis, preset_diff,  # noqa: E402
                 rules_engine, safety, threemf)

SRC = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
OUT = Path(r"F:\deep seek\鱼缸温度计支架\_test_diff_only.3mf")
MODE = sys.argv[1] if len(sys.argv) > 1 else "strength"


def main() -> int:
    proj = threemf.ThreeMfProject.load(SRC)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    prof = model_analysis.analyse(proj) if hasattr(model_analysis, "analyse") else None
    res = rules_engine.RulesEngine(rules).optimize(
        proj.settings, printer_key=det.printer_key, filament_key=det.filament_key,
        nozzle=0.4, mode_key=MODE, hardware_info=hw, model_profile=prof)
    written, _ = proj.apply(res.write_values)
    info = preset_diff.apply_to_project(proj, also=list(res.write_values.keys()))
    out = proj.save_as(OUT)
    print(f"写入 {len(written)} 项｜工艺差异声明 {info}")
    print("自检:", safety.self_check(out, res.write_values) or "通过")
    print("输出:", out)
    for k in ("layer_height", "wall_loops", "outer_wall_speed", "sparse_infill_pattern"):
        print(f"  {k:24} {res.values.get(k)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
