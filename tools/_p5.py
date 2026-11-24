"""把社区口径的 PETG 风扇建议写进交叉规则的提示文案（只提示，不写耗材页）。"""
import io
import json
import shutil
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"

WARN = (
    "PETG 层间强度与拉丝主要由耗材页决定，这里给出社区通行结论供你核对："
    "喷嘴 230~250℃、热床 80~90℃、零件风扇 20~50%（超过 50% 层间粘合会明显下降，"
    "但低于 20% 悬垂会塌）；空走速度保持机型高速（慢空走会让喷嘴在途中持续出料，"
    "越慢越拉丝），治拉丝靠回抽长度/速度、擦嘴、Z hop —— 这几项都在耗材页，本程序只读不改。"
    "工艺页这边已把斜切关闭（斜切会挂料）。"
)

rules = json.load(io.open(RULES, encoding="utf-8-sig"), object_pairs_hook=OrderedDict)
hit = 0
for it in rules["interactions"]:
    if it.get("id") == "petg-stringing":
        it["warn"] = WARN
        hit += 1
print("改动条数", hit)

bak = RULES.with_suffix(".json.bak_petgwarn")
shutil.copy2(RULES, bak)
io.open(RULES, "w", encoding="utf-8").write(
    json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
print("已写回", RULES.stat().st_size, "bytes")
