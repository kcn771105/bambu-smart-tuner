import io
import json
import sys
import zipfile
from _paths import project as _project, out as _out  # noqa: E402

sys.path.insert(0, ".")

SRC = str(_project())
OUT = str(_out("_test_diff_only.3mf"))

SPEED_KEYS = [
    "outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "gap_infill_speed",
    "travel_speed", "initial_layer_speed", "initial_layer_infill_speed",
    "bridge_speed", "overhang_2_4_speed", "support_speed",
]


def load(p):
    with zipfile.ZipFile(p) as z:
        return json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))


a, b = load(SRC), load(OUT)
print("键数 源/出:", len(a), len(b))
print()
for k in SPEED_KEYS:
    print(f"{k:32} 源={str(a.get(k, '<缺>')):28} 出={str(b.get(k, '<缺>'))}")
print()
d = b.get("different_settings_to_system")
if isinstance(d, str):
    d = json.loads(d)
proc = (d or ["", "", ""])[0]
declared = [x for x in proc.split(";") if x]
print("工艺槽声明数:", len(declared))
for k in SPEED_KEYS:
    print(f"   {k:32} 是否声明: {'✓' if k in declared else '✗'}")
