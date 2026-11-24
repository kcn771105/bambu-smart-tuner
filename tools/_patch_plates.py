"""给规则库补「打印板（板型 + 板面）」段，并给每个机型补官方板面尺寸。

板型名与官方 filament 预设的温度键对应关系（Bambu Studio 的 6 种板）：

    Cool Plate            cool_plate_temp       低温板，基本只适合 PLA
    Engineering Plate     eng_plate_temp        工程板，ABS/ASA 友好
    High Temp Plate       hot_plate_temp        高温板，ABS/ASA/PC
    Textured PEI Plate    textured_plate_temp   纹理 PEI
    Smooth PEI Plate      textured_plate_temp   光面 PEI（Bambu 复用纹理板温度键）
    Supertack Plate       supertack_plate_temp  超粘板（出厂默认）

关键事实：官方 filament 预设里，某条料不支持的板，对应温度是 `0`。
本工程实测：PETG 的 cool_plate_temp = 0，其余 70/70/80/60 —— 说明低温板不能跑 PETG。
这条规则直接当「板型 × 耗材」兼容性判据用，不用自己编。

板面尺寸取自官方 machine 预设的 printable_area / printable_height。

用法：python tools/_patch_plates.py [--apply]
"""
import io
import json
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

# 机型 → (宽, 深, 高)，来自官方 machine 预设 printable_area / printable_height
BEDS = OrderedDict([
    ("X1C", [256, 256, 256]),
    ("X1", [256, 256, 256]),
    ("X1E", [256, 256, 256]),
    ("P1S", [256, 256, 256]),
    ("P1P", [256, 256, 256]),
    ("P2S", [256, 256, 256]),
    ("P2P", [256, 256, 256]),
    ("A1", [256, 256, 256]),
    ("A1mini", [180, 180, 180]),
    ("H2D", [350, 320, 325]),
    ("H2DP", [350, 320, 325]),
    ("H2S", [340, 320, 340]),
    ("GENERIC", [220, 220, 250]),
])

PLATES = OrderedDict([
    ("Supertack Plate", OrderedDict([
        ("label", "Supertack 超粘板"),
        ("temp_key", "supertack_plate_temp"),
        ("aliases", ["Supertack Plate", "Supertack", "超粘板"]),
        ("note", "出厂默认板。附着力极强：PETG/TPU 打完容易连着板一起撕，"
                 "拆件前必须等降到 40℃ 以下；裙边不需要加宽，加了反而难拆。"),
        ("process", OrderedDict([
            ("brim_width", {"max": 4}),
            ("elefant_foot_compensation", {"min": 0.15}),
        ])),
    ])),
    ("Textured PEI Plate", OrderedDict([
        ("label", "纹理 PEI 板"),
        ("temp_key", "textured_plate_temp"),
        ("aliases", ["Textured PEI Plate", "Textured PEI", "纹理板", "PEI 纹理板"]),
        ("note", "纹理面首层实际接触面积比光面小，薄底/高瘦件要多给着地面；"
                 "PETG 在纹理面粘得很牢，拆件同样要等降温。"),
        ("process", OrderedDict([
            ("brim_width", {"min": 6}),
        ])),
    ])),
    ("Smooth PEI Plate", OrderedDict([
        ("label", "光面 PEI 板"),
        ("temp_key", "textured_plate_temp"),
        ("aliases", ["Smooth PEI Plate", "Smooth PEI", "光面板"]),
        ("note", "光面板首层接触充分，底面会有镜面效果；温度键与纹理板共用。"),
        ("process", OrderedDict()),
    ])),
    ("High Temp Plate", OrderedDict([
        ("label", "高温板"),
        ("temp_key", "hot_plate_temp"),
        ("aliases", ["High Temp Plate", "High Temperature Plate", "高温板"]),
        ("note", "耐高温板，ABS/ASA 大件首选；PLA 也能用，但降温后件会自己松开。"),
        ("process", OrderedDict()),
    ])),
    ("Engineering Plate", OrderedDict([
        ("label", "工程板"),
        ("temp_key", "eng_plate_temp"),
        ("aliases", ["Engineering Plate", "工程板"]),
        ("note", "工程材料板，ABS/ASA/PC 友好；表面不如 PEI 耐磨，别用金属铲。"),
        ("process", OrderedDict()),
    ])),
    ("Cool Plate", OrderedDict([
        ("label", "低温板"),
        ("temp_key", "cool_plate_temp"),
        ("aliases", ["Cool Plate", "Cool Board", "低温板"]),
        ("note", "低温板（出厂多为 PLA 专用）。官方预设里不支持的耗材，"
                 "该板温度是 0 —— 看到 0 就别在这个板上打这条料。"),
        ("process", OrderedDict()),
    ])),
])


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"),
                      object_pairs_hook=OrderedDict)

    for key, dims in BEDS.items():
        node = rules["printers"].get(key)
        if node is None:
            print("⚠ 规则库里没有机型", key)
            continue
        node["bed"] = dims

    rules["plates"] = OrderedDict([
        ("note", "板型 → 官方温度键 → 该板上的工艺微调。板型名来自工程 curr_bed_type；"
                 "温度取自耗材页 *_plate_temp（只读），为 0 表示这条料在该板上不可用。"),
        ("items", PLATES),
    ])

    print(f"机型板面：{len(BEDS)} 个；板型：{len(PLATES)} 种")
    if apply:
        shutil.copy2(RULES, RULES.with_suffix(".json.bak_plates"))
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print("已写回", RULES.stat().st_size, "bytes")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
