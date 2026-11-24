"""把官方「耗材 × 机型组 × 喷嘴」流量矩阵写进 rules/BambuRules.json。

数据来源：Bambu Studio 官方 filament 预设沿 inherits 链合并后取的
`filament_max_volumetric_speed` 第 0 槽（实测，见 tools/_dump_flow_matrix2.py）：

    Bambu PLA Basic   @BBL X1C          0.2→2   0.4→21  0.6→21  0.8→21
    Bambu PLA Basic   @BBL H2D          0.2→2   0.4→25  0.6→30  0.8→30
    Bambu PETG Basic  @BBL X1C          0.2→1   0.4→13  0.6→13  0.8→16
    Bambu PETG Basic  @BBL A1           0.2→1   0.4→9   0.6→9   0.8→12
    Bambu PETG Basic  @BBL H2D          0.2→1   0.4→13  0.6→16  0.8→16
    Bambu ABS         @BBL X1C/P2S      0.2→2   0.4→16  0.6→16  0.8→18
    Bambu ABS         @BBL H2D          0.2→2   0.4→20  0.6→25  0.8→25
    Bambu ASA         @BBL X1C/P2S/A1   0.2→2   0.4→18  0.6→18  0.8→18
    Bambu ASA         @BBL H2D          0.2→2   0.4→20  0.6→25  0.8→25
    Bambu TPU 95A     全系所有喷嘴        3.6

用法：python tools/_patch_nozzle_flow.py [--apply]
"""
import io
import json
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

NOTE = (
    "官方 filament 预设的 filament_max_volumetric_speed 是「按喷嘴」给的："
    "Bambu PETG Basic 在 X1C 上 0.2 喷嘴只有 1 mm³/s、0.4 是 13、0.8 是 16。"
    "换喷嘴不换流量上限，0.2 喷嘴就会按 0.4 的流量算速度，轻则表面糊、重则堵料。"
    "本表由 tools/_dump_flow_matrix2.py 从官方预设读出，改喷嘴时引擎按它折算。"
)

TABLE = OrderedDict([
    ("X1", OrderedDict([
        ("PLA",  OrderedDict([("0.2", 2), ("0.4", 21), ("0.6", 21), ("0.8", 21)])),
        ("PETG", OrderedDict([("0.2", 1), ("0.4", 13), ("0.6", 13), ("0.8", 16)])),
        ("ABS",  OrderedDict([("0.2", 2), ("0.4", 16), ("0.6", 16), ("0.8", 18)])),
        ("ASA",  OrderedDict([("0.2", 2), ("0.4", 18), ("0.6", 18), ("0.8", 18)])),
        ("TPU",  OrderedDict([("0.2", 3.6), ("0.4", 3.6), ("0.6", 3.6), ("0.8", 3.6)])),
    ])),
    ("P2", OrderedDict([
        ("PLA",  OrderedDict([("0.2", 2), ("0.4", 21), ("0.6", 21), ("0.8", 21)])),
        ("PETG", OrderedDict([("0.2", 1), ("0.4", 13), ("0.6", 16), ("0.8", 16)])),
        ("ABS",  OrderedDict([("0.2", 2), ("0.4", 16), ("0.6", 16), ("0.8", 18)])),
        ("ASA",  OrderedDict([("0.2", 2), ("0.4", 18), ("0.6", 18), ("0.8", 18)])),
        ("TPU",  OrderedDict([("0.2", 3.6), ("0.4", 3.6), ("0.6", 3.6), ("0.8", 3.6)])),
    ])),
    ("A1", OrderedDict([
        ("PLA",  OrderedDict([("0.2", 2), ("0.4", 21), ("0.6", 21), ("0.8", 21)])),
        ("PETG", OrderedDict([("0.2", 1), ("0.4", 9), ("0.6", 9), ("0.8", 12)])),
        ("ABS",  OrderedDict([("0.2", 2), ("0.4", 16), ("0.6", 16), ("0.8", 16)])),
        ("ASA",  OrderedDict([("0.2", 2), ("0.4", 18), ("0.6", 18), ("0.8", 18)])),
        ("TPU",  OrderedDict([("0.2", 3.6), ("0.4", 3.6), ("0.6", 3.6), ("0.8", 3.6)])),
    ])),
    ("H2", OrderedDict([
        ("PLA",  OrderedDict([("0.2", 2), ("0.4", 25), ("0.6", 30), ("0.8", 30)])),
        ("PETG", OrderedDict([("0.2", 1), ("0.4", 13), ("0.6", 16), ("0.8", 16)])),
        ("ABS",  OrderedDict([("0.2", 2), ("0.4", 20), ("0.6", 25), ("0.8", 25)])),
        ("ASA",  OrderedDict([("0.2", 2), ("0.4", 20), ("0.6", 25), ("0.8", 25)])),
        ("TPU",  OrderedDict([("0.2", 3.6), ("0.4", 3.6), ("0.6", 3.6), ("0.8", 3.6)])),
    ])),
    ("GENERIC", OrderedDict([
        ("PLA",  OrderedDict([("0.2", 2), ("0.4", 15), ("0.6", 15), ("0.8", 15)])),
        ("PETG", OrderedDict([("0.2", 1), ("0.4", 8), ("0.6", 8), ("0.8", 10)])),
        ("ABS",  OrderedDict([("0.2", 2), ("0.4", 12), ("0.6", 12), ("0.8", 12)])),
        ("ASA",  OrderedDict([("0.2", 2), ("0.4", 12), ("0.6", 12), ("0.8", 12)])),
        ("TPU",  OrderedDict([("0.2", 3.6), ("0.4", 3.6), ("0.6", 3.6), ("0.8", 3.6)])),
    ])),
])


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"),
                      object_pairs_hook=OrderedDict)
    rules["nozzle_flow"] = OrderedDict([
        ("note", NOTE),
        ("nozzles", ["0.2", "0.4", "0.6", "0.8"]),
        ("by_group", TABLE),
        ("nozzle_volume", OrderedDict([
            ("note", "机器页 nozzle_volume（熔池体积 mm³）随机型，不随喷嘴变；"
                     "H2D/H2D Pro 有多槽（130/133/145/148 对应不同热端），取第 0 槽。"),
            ("X1", 107), ("P1", 107), ("P2", 110), ("A1", 92),
            ("H2", 130), ("GENERIC", 0),
        ])),
    ])
    print(f"喷嘴流量矩阵：{len(TABLE)} 组 × {len(next(iter(TABLE.values())))} 耗材 × 4 喷嘴")
    if apply:
        shutil.copy2(RULES, RULES.with_suffix(".json.bak_nozflow"))
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print("已写回", RULES.stat().st_size, "bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
