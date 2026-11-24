import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, rules_engine, threemf  # noqa: E402

PROJ = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


def main() -> int:
    proj = threemf.ThreeMfProject.load(PROJ)
    rules = rules_engine.load_rules()
    hw = hardware.read(proj)
    det = detector.detect(proj, rules)

    print(f"工程 nozzle_volume_type = {proj.settings.get('nozzle_volume_type')}")
    print(f"{'流量类型':10} {'流量上限':>8} {'外壁':>7} {'内壁':>7} {'层高':>6} {'时长':>8}")
    for flow in (None, "standard", "high", "e3d"):
        eng = rules_engine.RulesEngine(rules)
        res = eng.optimize(proj.settings, printer_key=det.printer_key,
                           filament_key=det.filament_key, nozzle=0.4,
                           mode_key="balanced", hardware_info=hw,
                           hotend_flow=flow)
        out_v = res.values.get("outer_wall_speed")
        in_v = res.values.get("inner_wall_speed")
        t = getattr(res, "time", None)
        pct = getattr(t, "pct", None) if t is not None else None
        print(f"{str(flow):10} {res.flow_limit or 0:8.1f} {out_v!s:>7} {in_v!s:>7} "
              f"{res.values.get('layer_height'):>6} {'' if pct is None else f'{pct:+.1f}%':>8}")
        for n in res.notes:
            if "热端流量类型" in n:
                print("     ", n[:110])
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
