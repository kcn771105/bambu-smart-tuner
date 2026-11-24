import io
import json
import sys

sys.path.insert(0, ".")

from core import hardware
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject

SRC = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"
rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
p = ThreeMfProject.load(SRC)
hw = hardware.read(p)
res = eng.optimize(p.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                   mode_key="balanced", hardware_info=hw, nozzle_explicit=True)

print("enable_support 写入：", res.write_values.get("enable_support", "未写"))
print("支撑相关 note：")
for n in res.notes:
    if "支撑" in n or "悬垂" in n:
        print("   ", n)
print("支撑相关 warning：")
for w in res.warnings:
    if "支撑" in w or "悬垂" in w:
        print("   ", w)
print()
print("推导表里的支撑/裙边行：")
for d in res.derivations:
    if any(t in str(d.get("metric", "")) for t in ("支撑", "裙边", "悬垂", "倾覆")):
        print("   ", d.get("metric"), "|", d.get("measured"), "|", d.get("formula"), "|", d.get("conclusion"))
