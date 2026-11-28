"""验证「换喷嘴 → 流量上限跟着换」。

注意：`optimize(..., nozzle_explicit=True)` 才表示「用户手动改过喷嘴」；
不传时引擎会以工程 machine 页的 nozzle_diameter 为准（这是同步逻辑）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, rules_engine, threemf  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

PROJ = _project()


def main() -> int:
    proj = threemf.ThreeMfProject.load(PROJ)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)

    print(f"工程喷嘴 {hw.nozzle_diameter} mm｜耗材 {det.filament_key}｜"
          f"工程标定流量 {hw.max_volumetric_speed} mm³/s｜"
          f"熔池 {hw.nozzle_volume} mm³\n")
    head = (f"{'喷嘴':>6s}{'流量上限':>10s}{'外壁':>8s}{'内壁':>8s}"
            f"{'填充':>8s}{'层高':>7s}{'线宽':>7s}")
    print(head)
    print("-" * len(head.encode("gbk", "ignore")))
    for noz in (0.2, 0.4, 0.6, 0.8):
        res = eng.optimize(proj.settings, printer_key=det.printer_key,
                           filament_key=det.filament_key, nozzle=noz,
                           mode_key="balanced", hardware_info=hw,
                           nozzle_explicit=True)
        v = res.values
        print(f"{noz:>6.1f}{eng._flow_limit or 0:>10.1f}"
              f"{v.get('outer_wall_speed', 0):>8.1f}"
              f"{v.get('inner_wall_speed', 0):>8.1f}"
              f"{v.get('sparse_infill_speed', 0):>8.1f}"
              f"{v.get('layer_height', 0):>7.2f}"
              f"{v.get('line_width', 0):>7.2f}")
        for w in res.warnings:
            if "喷嘴同步" in w:
                print("       ↳", w[:160])
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
