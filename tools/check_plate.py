"""验证打印板同步：板型识别 / 兼容性 / 板面尺寸 / 模型放得下吗 / 板型工艺微调。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, plate, rules_engine, threemf  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

PROJ = _project()


def main() -> int:
    proj = threemf.ThreeMfProject.load(PROJ)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    info = plate.read(proj, rules)
    print("板型识别：", info.summary_line())
    print("工程原值 curr_bed_type =", proj.settings.get("curr_bed_type"))
    print()

    profile = model_analysis.analyse(proj)
    print("—— 正常情况（P2S + PETG + Supertack）")
    w, n, o = plate.check(info, rules=rules, printer_key="P2S",
                          filament_key="PETG", profile=profile)
    print("  警告:", w or "无")
    for x in n:
        print("  说明:", x)
    print("  工艺微调:", o)
    print()

    print("—— 把板型改成低温板（官放 PETG 在该板温度为 0）")
    proj2 = threemf.ThreeMfProject.load(PROJ)
    proj2.settings["curr_bed_type"] = "Cool Plate"
    info2 = plate.read(proj2, rules)
    w2, n2, _ = plate.check(info2, rules=rules, printer_key="P2S",
                            filament_key="PETG", profile=profile)
    print("  ", info2.summary_line())
    for x in w2:
        print("  警告:", x)
    print()

    print("—— 机型识别成 A1 mini（板面 180×180 对不上 256×256）")
    w3, _n, _ = plate.check(info, rules=rules, printer_key="A1mini",
                            filament_key="PETG", profile=profile)
    for x in w3:
        print("  警告:", x)
    print()

    print("—— 引擎全链路（均衡模式）")
    eng = rules_engine.RulesEngine(rules)
    res = eng.optimize(proj.settings, printer_key=det.printer_key,
                       filament_key=det.filament_key, nozzle=0.4,
                       mode_key="balanced", hardware_info=hw,
                       model_profile=profile)
    print("  plate =", res.plate)
    print("  板相关说明：")
    for x in res.notes:
        if "打印板" in x or "板面" in x or "禁打区" in x:
            print("   ·", x)
    print("  brim_width =", res.values.get("brim_width"),
          " elefant_foot =", res.values.get("elefant_foot_compensation"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

