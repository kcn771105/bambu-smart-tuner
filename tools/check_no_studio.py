"""模拟「目标机器没装 Bambu Studio」的情况：预设目录不存在时能不能正常出文件。"""
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, ".")

from core import hardware, preset_diff, safety
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject

SRC = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

# 把 Studio 预设目录指到一个空目录，模拟没装 Studio
empty = Path(tempfile.mkdtemp())
preset_diff.STUDIO_DIRS = (empty,)
preset_diff._CACHE.clear()

print("find_preset →", preset_diff.find_preset("0.20mm Standard @BBL P2S", "process"))

rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
p = ThreeMfProject.load(SRC)
hw = hardware.read(p)
res = eng.optimize(p.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                   mode_key="balanced", hardware_info=hw, nozzle_explicit=True)
p.apply(res.write_values)
info = preset_diff.apply_to_project(p, also=list(res.write_values.keys()))
print("差异声明 →", info)

out = Path(tempfile.mkdtemp()) / "no_studio.3mf"
p.save_as(out)
with zipfile.ZipFile(out) as z:
    d = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
tri = d["different_settings_to_system"]
if isinstance(tri, str):
    tri = json.loads(tri)
print("工艺槽声明数 →", len([x for x in tri[0].split(";") if x]))
print("自检 →", safety.self_check(out, res.write_values) or "通过")
print("文件大小 →", out.stat().st_size)
