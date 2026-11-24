import io
import json
import sys

sys.path.insert(0, ".")

from core import hardware, model_analysis
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject

prj = ThreeMfProject.load(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
hw = hardware.read(prj)
prof = model_analysis.analyse(prj)

for mode in ("strength", "quality"):
    res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                       mode_key=mode, hardware_info=hw, nozzle_explicit=True,
                       model_profile=prof)
    keys = ["support_speed", "support_interface_speed", "support_line_width",
            "support_top_z_distance", "support_object_xy_distance",
            "support_base_pattern_spacing", "support_interface_spacing",
            "support_type", "support_style"]
    print(f"=== {mode}")
    for k in keys:
        if k in res.write_values:
            print(f"   {k:32} = {res.write_values[k]}")
    print()
