"""收敛 hotend_flow 段：只保留真正参与计算的一维（volumetric_mul）。

理由：高流量热端省下来的时间是「同样流量下能跑更快」，这件事在引擎里已经由
「流量上限 ↑ → _clamp_flow 允许更快的速度」自动体现。再单独乘一个 speed_mul
等于同一件事算两遍，会让速度越过机器上限、也会把时长估算压低得不真实。
所以 speed_mul 从规则库删掉，hardend.speed_factor 也从代码里去掉。
"""
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "BambuRules.json"


def main() -> int:
    apply = "--apply" in sys.argv
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))
    sec = rules.get("hotend_flow") or {}
    for key, node in (sec.get("types") or {}).items():
        node.pop("speed_mul", None)
    sec["note"] = (
        "热端流量类型：标准流量 / 高流量 / E3D 高流量。"
        "volumetric_mul 只作用在「体积流量上限」上，且强制 ≥ 1.0（识别不出来也不会把高流量热端压回去）。"
        "高流量省下的时间由「流量上限 ↑ → 允许更快的速度」自动体现，不再单独乘速度倍率。")
    print("types:", list((sec.get("types") or {})))
    for k, node in (sec.get("types") or {}).items():
        print("  ", k, node)
    if apply:
        shutil.copy2(RULES, RULES.with_suffix(".json.bak_hotend2"))
        io.open(RULES, "w", encoding="utf-8").write(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n")
        print("已写回", RULES.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
