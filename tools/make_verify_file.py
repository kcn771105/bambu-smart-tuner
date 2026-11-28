"""用新写入路径出一份文件，供 Bambu Studio 打开验证。

流程与 UI 保存完全一致：optimize → apply → mark_custom_process → save_as → self_check
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import (detector, hardware, preset_diff, rules_engine,  # noqa: E402
                  safety, threemf)
from _paths import project as _project, out as _out  # noqa: E402

SRC = _project()
OUT = _out("本地工程_smarttuner_verify.3mf")
MODE = sys.argv[1] if len(sys.argv) > 1 else "strength"


def main() -> int:
    proj = threemf.ThreeMfProject.load(SRC)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)
    res = eng.optimize(proj.settings, printer_key=det.printer_key,
                       filament_key=det.filament_key, nozzle=0.4,
                       mode_key=MODE, hardware_info=hw)

    written, skipped = proj.apply(res.write_values)
    info = preset_diff.apply_to_project(proj, also=list(res.write_values.keys()))
    renamed = proj.mark_custom_process()
    out = proj.save_as(OUT)

    problems = safety.self_check(out, res.write_values)
    print(f"模式 {MODE}：写入 {len(written)} 项，跳过 {skipped}")
    print(f"工艺差异声明：{info}")
    print(f"工艺档改名：{renamed}")
    print(f"输出：{out}")
    print(f"自检：{'通过' if not problems else problems}")
    for k in ("layer_height", "wall_loops", "outer_wall_speed", "sparse_infill_density",
              "sparse_infill_pattern", "inner_wall_speed"):
        print(f"  {k:26} {res.values.get(k)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
