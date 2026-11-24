"""把热端流量类型写进规则库（hotend_flow 段）。

倍率依据：
    Bambu 官方 High Flow 热端（P2S / X1 选装）标称比标准热端流量高约 30~40%，
    E3D 高流量（X1E / H2D 选装）再高一些，约 50~60%。
    这里取保守值：high → 1.35 / speed 1.15；e3d → 1.55 / speed 1.20。
    缩小时一律不允许（factor 在 core/hotend.py 里强制 ≥ 1.0），
    因为「识别成标准」不该把高流量热端的能力压回去。
"""
import io
import json
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

SECTION = OrderedDict([
    ("note", "热端流量类型：标准流量 / 高流量 / E3D 高流量。"
             "倍率只放宽不收紧 —— 标准热端就是 1.0，识别不出来也不会把高流量热端压回去。"
             "volumetric_mul 作用在「体积流量上限」，speed_mul 作用在「速度基准」。"),
    ("types", OrderedDict([
        ("standard", OrderedDict([
            ("label", "标准流量"),
            ("volumetric_mul", 1.0),
            ("speed_mul", 1.0),
            ("note", "官方 filament_max_volumetric_speed 就是按标准热端标的，直接采用。"),
        ])),
        ("high", OrderedDict([
            ("label", "高流量"),
            ("volumetric_mul", 1.35),
            ("speed_mul", 1.15),
            ("note", "Bambu High Flow 热端熔池更大，官方标称流量约 +30~40%；"
                     "取 1.35 保守值。高流量热端压力提前通常也要 +10~20%，属耗材页只读，不在此调。"),
        ])),
        ("e3d", OrderedDict([
            ("label", "E3D 高流量"),
            ("volumetric_mul", 1.55),
            ("speed_mul", 1.20),
            ("note", "E3D 结构流量更高（约 +50~60%），取 1.55；"
                     "但回抽与压力提前对 E3D 更敏感，回抽参数属耗材页只读，不在此调。"),
        ])),
    ])),
])


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"),
                      object_pairs_hook=OrderedDict)
    rules["hotend_flow"] = SECTION
    print("hotend_flow 段：", list(SECTION["types"]))
    if apply:
        shutil.copy2(RULES, RULES.with_suffix(".json.bak_hotend"))
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print("已写回", RULES.stat().st_size, "bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
