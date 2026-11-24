import sys

sys.path.insert(0, ".")
from core import adhesion, detector, hardware, model_analysis, rules_engine, threemf

P = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"
proj = threemf.ThreeMfProject.load(P)
rules = rules_engine.load_rules()
mp = model_analysis.analyse(proj)

ops, notes, rows = adhesion.tune(mp, line_width=0.42, layer_height=0.2,
                                 filament_key="PETG", mode="balanced",
                                 current=dict(proj.settings))
print("adhesion ops:", ops)
print("notes:", notes[:3])

eng = rules_engine.RulesEngine(rules)
det = detector.detect(proj, rules)
res = eng.optimize(proj.settings, printer_key=det.printer_key,
                   filament_key=det.filament_key, nozzle=det.nozzle,
                   mode_key="balanced", model_profile=mp,
                   hardware_info=hardware.read(proj), nozzle_explicit=True)
for k in ("brim_width", "brim_type", "brim_object_gap"):
    print(k, "value=", res.values.get(k), "write=", k in res.write_values)
    print("   reasons:", res.reasons.get(k))
