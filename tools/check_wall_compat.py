import sys

sys.path.insert(0, ".")
from core import wall_compat

# 1) 工程开着交替额外墙、墙层数被抬到 6 → 应关掉交替额外墙
ops, warns, notes = wall_compat.check(
    {"wall_loops": 6}, project={"alternate_extra_wall": "1", "wall_loops": "2",
                                "ensure_vertical_shell_thickness": "enabled"})
print("A ops=", ops)
print("A warn=", warns[0][:60] if warns else None)

# 2) 墙层数保持 2、外壳不是 partial → 应补 partial
ops2, warns2, notes2 = wall_compat.check(
    {"wall_loops": 2}, project={"alternate_extra_wall": "1", "wall_loops": "2",
                                "ensure_vertical_shell_thickness": "enabled"})
print("B ops=", ops2)

# 3) 已经是 partial → 不动
ops3, _, notes3 = wall_compat.check(
    {"wall_loops": 2}, project={"alternate_extra_wall": "1",
                                "ensure_vertical_shell_thickness": "partial"})
print("C ops=", ops3)

# 4) 没开交替额外墙 → 完全不动
ops4, _, _ = wall_compat.check({"wall_loops": 6}, project={"alternate_extra_wall": "0"})
print("D ops=", ops4)

# 5) 引擎端到端
import io
import json

from core import hardware
from core.rules_engine import RulesEngine
from core.threemf import ThreeMfProject
from _paths import project as _project, out as _out  # noqa: E402

rules = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
eng = RulesEngine(rules)
p = ThreeMfProject.load(str(_project()))
p.settings["alternate_extra_wall"] = "1"   # 模拟用户在 Studio 里勾上这个选项
hw = hardware.read(p)
r = eng.optimize(p.settings, printer_key="P2S", filament_key="PETG", nozzle=0.4,
                 mode_key="strength", hardware_info=hw, nozzle_explicit=True)
print("E 写入 alternate_extra_wall =", r.write_values.get("alternate_extra_wall", "未写"))
print("E 墙层数 =", r.write_values.get("wall_loops"))
print("E 警告含交替额外墙 =", any("交替额外墙" in w for w in r.warnings))
