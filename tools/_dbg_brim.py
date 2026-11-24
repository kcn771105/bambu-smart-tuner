import sys

sys.path.insert(0, ".")
from core import detector, hardware, model_analysis, rules_engine, threemf

P = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"
proj = threemf.ThreeMfProject.load(P)
rules = rules_engine.load_rules()
det = detector.detect(proj, rules)
hw = hardware.read(proj)
mp = model_analysis.analyse(proj)
eng = rules_engine.RulesEngine(rules)

for mode in ("balanced", "strength"):
    res = eng.optimize(proj.settings, printer_key=det.printer_key,
                       filament_key=det.filament_key, nozzle=det.nozzle,
                       mode_key=mode, model_profile=mp, hardware_info=hw,
                       nozzle_explicit=True)
    print(f"===== {mode} =====")
    for k in ("brim_width", "brim_type", "brim_object_gap", "enable_support",
              "support_base_pattern_spacing", "support_top_z_distance",
              "support_object_xy_distance", "support_type", "support_style",
              "support_interface_spacing", "support_threshold_angle"):
        print(f"  {k:32} cur={str(proj.settings.get(k)):12} -> {res.values.get(k)}"
              f"  write={k in res.write_values}")
    print("  --- 推导行（裙边/支撑）---")
    for d in res.derivations:
        if "裙边" in d["metric"] or "支撑" in d["metric"]:
            print("   ", d["metric"], "|", d["measured"], "|", d["conclusion"])
