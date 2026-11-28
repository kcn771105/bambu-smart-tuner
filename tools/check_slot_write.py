import io
import json
import sys
import zipfile

sys.path.insert(0, ".")

from core import hardware
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject
from _paths import project as _project, out as _out  # noqa: E402

SRC = str(_project())
OUT = str(_out("_test_slots.3mf"))

rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
p = ThreeMfProject.load(SRC)
hw = hardware.read(p)
res = eng.optimize(p.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                   mode_key="balanced", hardware_info=hw, nozzle_explicit=True)
print("写入项数:", len(res.write_values))
for k in ("outer_wall_speed", "inner_wall_speed", "travel_speed", "default_acceleration"):
    print(f"  {k:26}", res.write_values.get(k, "未写"))

p.apply(res.write_values)
p.save_as(OUT)
with zipfile.ZipFile(OUT) as z:
    out = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
with zipfile.ZipFile(SRC) as z:
    src = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
print()
for k in ("outer_wall_speed", "inner_wall_speed", "travel_speed", "default_acceleration"):
    print(f"  {k:26} 源={src.get(k)}  出={out.get(k)}")
