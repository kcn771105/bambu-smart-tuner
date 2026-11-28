import io
import json
import sys

sys.path.insert(0, ".")

from core import hardware, model_analysis
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject
from _paths import project as _project, out as _out  # noqa: E402

SRC = str(_project())
rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
prj = ThreeMfProject.load(SRC)
hw = hardware.read(prj)
prof = model_analysis.analyse(prj)
print("profile:", type(prof).__name__ if prof else None)

for mode in ("strength", "balanced", "quality", "draft"):
    res = eng.optimize(prj.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                       mode_key=mode, hardware_info=hw, nozzle_explicit=True,
                       model_profile=prof)
    sup = {k: v for k, v in res.write_values.items()
           if k.startswith(("support_", "tree_support_", "enable_support"))}
    print(f"[{mode}] {len(sup)} 项 →", json.dumps(sup, ensure_ascii=False))
    print()
