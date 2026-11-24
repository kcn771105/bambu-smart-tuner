"""机型矩阵巡检：13 个机型 × 6 档模式 全跑一遍，查崩溃/越界/时长。

用法：python tools/check_all_printers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, rules_engine, schema, threemf  # noqa: E402

PROJECT = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


def main() -> int:
    proj = threemf.ThreeMfProject.load(PROJECT)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)
    prof = model_analysis.analyse(
        proj, overhang_angle=float(proj.settings.get("support_threshold_angle", 45) or 45),
        layer_height=float(proj.settings.get("layer_height", 0.2) or 0.2))

    modes = [m[0] for m in eng.mode_choices()]
    printers = list(rules["printers"].keys())
    print(f"机型 {len(printers)} × 模式 {len(modes)} = {len(printers) * len(modes)} 组\n")
    print(f"{'机型':<10s}{'模式':<12s}{'写入':>5s}{'越界':>5s}{'时长':>10s}")
    bad = 0
    for p in printers:
        for m in modes:
            try:
                res = eng.optimize(proj.settings, printer_key=p,
                                   filament_key=det.filament_key, nozzle=det.nozzle,
                                   mode_key=m, model_profile=prof, hardware_info=hw)
            except Exception as exc:  # noqa: BLE001
                print(f"{p:<10s}{m:<12s}  ✗ 崩了：{exc}")
                bad += 1
                continue
            viol = 0
            for k, raw in res.values.items():
                s = schema.PARAMS.get(k)
                if s is None or s.kind in (schema.ENUM, schema.BOOL) or s.kind.startswith("ARRAY") or k.startswith("ENUM_"):
                    continue
                if not isinstance(raw, (int, float)):
                    continue
                if raw < s.vmin - 1e-9 or raw > s.vmax + 1e-9:
                    viol += 1
            if viol:
                bad += 1
            print(f"{p:<10s}{m:<12s}{len(res.write_values):>5d}{viol:>5d}"
                  f"{res.time.delta_pct:>9.1f}%")
    print(f"\n异常组合：{bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
