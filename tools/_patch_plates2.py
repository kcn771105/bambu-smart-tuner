"""板型工艺微调只碰「非 preserve」的键。

踩坑：`brim_width` 在 schema 里是 `preserve=True`（用户自己定的值不许动），
板层写它会被静默跳过 —— 既不生效也不报错，等于白写。
所以：
    - Supertack / Textured 只留 `elefant_foot_compensation`（不是 preserve）；
    - 裙边建议改成文字 advice，写进说明而不是硬改参数。
"""
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

PROCESS = {
    "Supertack Plate": {"elefant_foot_compensation": {"min": 0.15}},
    "Textured PEI Plate": {},
    "Smooth PEI Plate": {},
    "High Temp Plate": {},
    "Engineering Plate": {},
    "Cool Plate": {},
}

ADVICE = {
    "Supertack Plate": "超粘板不需要为附着加宽裙边（越宽越难拆、撕涂层风险越大）；"
                       "若细高件被形状层加了裙边，那是稳定性优先，打完等降到 40℃ 以下再取件。",
    "Textured PEI Plate": "纹理面首层实际接触面积比光面小：薄底/高瘦件建议手动把裙边加到 6~8 mm。",
    "Smooth PEI Plate": "光面板首层接触充分，裙边按形状层给的就行。",
    "High Temp Plate": "高温板降温后会自己松开，不用为拆件改参数。",
    "Engineering Plate": "工程板别用金属铲，参数上无需改动。",
    "Cool Plate": "低温板基本只适合 PLA；这条料若在官方预设里温度为 0，就不要在这个板上打。",
}


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))
    items = rules["plates"]["items"]
    for key, proc in PROCESS.items():
        node = items.get(key)
        if node is None:
            print("⚠ 缺板型", key)
            continue
        node["process"] = proc
        node["advice"] = ADVICE[key]
    print("板型工艺微调已收敛：", {k: len(v) for k, v in PROCESS.items()})
    if apply:
        shutil.copy2(RULES, RULES.with_suffix(".json.bak_plates2"))
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print("已写回", RULES.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
