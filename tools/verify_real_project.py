"""真实工程复验：六档模式的改动数、时长、总闸触发、定量推导明细。

用法：
    python tools/verify_real_project.py [工程路径] [--printer KEY]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, rules_engine, threemf  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

DEFAULT_PROJECT = _project()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    project_path = Path(args[0]) if args else DEFAULT_PROJECT
    printer_override = ""
    for a in sys.argv[1:]:
        if a.startswith("--printer="):
            printer_override = a.split("=", 1)[1]

    proj = threemf.ThreeMfProject.load(project_path)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    current = proj.settings

    printer_key = printer_override or det.printer_key
    filament_key = det.filament_key
    nozzle = det.nozzle

    print(f"工程：{project_path.name}  键数 {len(current)}")
    print(f"识别：机型 {printer_key} / 耗材 {filament_key} / 喷嘴 {nozzle:g} mm")
    print(f"真机：{hw.summary_lines()[0] if hw.summary_lines() else ''}")

    profile = None
    try:
        profile = model_analysis.analyse(
            proj, overhang_angle=float(current.get("support_threshold_angle", 45) or 45),
            layer_height=float(current.get("layer_height", 0.2) or 0.2))
        print(f"模型：{profile.summary()}")
        for s in profile.object_summaries():
            print("   ", s)
    except Exception as exc:
        print(f"模型分析失败：{exc}")

    eng = rules_engine.RulesEngine(rules)
    print()
    print(f"{'模式':12s}{'写入':>6s}{'越界':>6s}{'时长':>9s}{'警告':>6s}{'总闸':>6s}{'推导':>6s}")
    for mode in eng.mode_choices():
        mk = mode[0]
        res = eng.optimize(current, printer_key=printer_key, filament_key=filament_key,
                           nozzle=nozzle, mode_key=mk, model_profile=profile,
                           hardware_info=hw, time_cap_pct=None)
        gate = sum(1 for w in res.warnings if w.startswith("叠乘总闸"))
        print(f"{mk:12s}{len(res.write_values):>6d}"
              f"{sum(1 for w in res.warnings if '越界' in w):>6d}"
              f"{res.time.delta_pct:>+8.1f}%{len(res.warnings):>6d}{gate:>6d}"
              f"{len(res.derivations):>6d}")
        if mk == "balanced":
            print("    —— 定量推导明细 ——")
            for d in res.derivations:
                print(f"    · {d['metric']}")
                print(f"        实测 {d['measured']}")
                print(f"        公式 {d['formula']}")
                print(f"        结论 {d['conclusion']}")
            for w in res.warnings:
                print("    ! " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
