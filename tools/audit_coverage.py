"""盘点：Bambu Studio 到底有哪些切片参数，本程序覆盖了多少。

数据源（都取本机真实文件）：
  1. 用户已有的工程 3mf 的 Metadata/project_settings.config（最权威，切片器真吃的键）
  2. C:\\Program Files\\Bambu Studio\\resources\\profiles\\BBL 下 process/filament/machine
     全部预设解析继承链后的键并集

输出：
  - 覆盖 / 未覆盖清单（按参数族）
  - 未覆盖项按「是否值得可调」分类
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema   # noqa: E402

PROF = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")
INDEX = PROF.parent / "BBL.json"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def resolve_chain(index: dict, name: str, base: Path) -> dict:
    by_name = {e["name"]: e["sub_path"] for e in
               index["machine_list"] + index["filament_list"] + index["process_list"]}
    chain, cur, seen = [], name, set()
    while cur and cur not in seen:
        seen.add(cur)
        sub = by_name.get(cur)
        if not sub:
            break
        d = load(base / sub)
        if not d:
            break
        chain.append(d)
        cur = d.get("inherits")
    merged = {}
    for d in reversed(chain):
        merged.update(d)
    return merged


def keys_from_profiles() -> dict[str, set[str]]:
    """返回 {来源: 键集合}，process / filament / machine 分开算。"""
    out: dict[str, set[str]] = defaultdict(set)
    if not INDEX.exists():
        return out
    index = load(INDEX)
    if not index:
        return out
    for kind, listkey in (("process", "process_list"),
                          ("filament", "filament_list"),
                          ("machine", "machine_list")):
        names = [e["name"] for e in index[listkey]]
        # 只取「可实例化」的预设（带具体机型/喷嘴的），基类不产生工程键
        picked = [n for n in names if not n.endswith("@base") and "nozzle" in n][:400]
        if kind != "machine":
            picked = [n for n in names if not n.endswith("@base")][:400]
        for n in picked:
            m = resolve_chain(index, n, PROF)
            out[kind].update(m.keys())
    return out


def keys_from_projects() -> set[str]:
    """从本机已有工程 3mf 里读 project_settings.config 的键。"""
    keys: set[str] = set()
    roots = [Path(os.environ.get("USERPROFILE", "")) / d for d in
             ("Desktop", "Downloads", "Documents")]
    # 别人跑这个脚本时这些路径不存在，会自动跳过；要扫别的目录就设 BST_SCAN_DIR
    for extra in (os.environ.get("BST_SCAN_DIR"),):
        if extra:
            roots.append(Path(extra).expanduser())
    roots.append(Path(os.environ.get("APPDATA", "")) / "BambuStudio")
    found = 0
    sys.path.insert(0, str(ROOT))
    from core import threemf
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*.3mf"):
            if found >= 12:
                break
            try:
                proj = threemf.ThreeMfProject.load(p)
            except Exception:
                continue
            keys.update(proj.settings.keys())
            found += 1
    print(f"[信息] 扫描到 {found} 个可用工程 3mf")
    return keys


NOISE_PREFIX = (
    "filament_", "machine_", "nozzle_", "printer_", "bed_", "extruder_",
    "upward_", "slow_down_", "reduce_fan", "hot_plate", "cool_plate",
    "textured_plate", "eng_plate", "supertack_plate", "curr_", "wipe_tower_",
    "default_", "auxiliary_", "ooze_", "scan_", "spiral_mode", "ironing",
)


def main() -> int:
    have = set(schema.PARAMS)
    prof = keys_from_profiles()
    proj = keys_from_projects()

    universe: set[str] = set()
    for v in prof.values():
        universe |= v
    universe |= proj

    print()
    print(f"Bambu Studio 预设里出现的键：process {len(prof.get('process', set()))} / "
          f"filament {len(prof.get('filament', set()))} / machine {len(prof.get('machine', set()))}")
    print(f"真实工程 3mf 里的键：{len(proj)}")
    print(f"总并集：{len(universe)}   本程序已声明：{len(have)}")
    print(f"覆盖率：{len(have & universe)} / {len(universe)} = {len(have & universe)/max(1,len(universe))*100:.1f}%")
    print()

    missing = sorted(universe - have)
    extra = sorted(have - universe)

    print(f"=== 未声明的键（{len(missing)} 个）===")
    buckets: dict[str, list[str]] = defaultdict(list)
    for k in missing:
        if k in proj:
            buckets["① 真工程里存在（切片器会读）"].append(k)
        elif k in prof.get("process", set()):
            buckets["② 只在 process 预设里"].append(k)
        elif k in prof.get("filament", set()):
            buckets["③ 只在 filament 预设里"].append(k)
        elif k in prof.get("machine", set()):
            buckets["④ 只在 machine 预设里"].append(k)
        else:
            buckets["⑤ 其他"].append(k)
    for b in sorted(buckets):
        items = buckets[b]
        print(f"\n{b}：{len(items)} 个")
        for k in items:
            print("   ", k)

    print(f"\n=== 已声明但预设里没出现的键（{len(extra)} 个，可能是版本差异）===")
    for k in extra:
        print("   ", k)

    # 落一份清单，方便后续补
    out = ROOT / "shots" / "key_audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "universe": sorted(universe),
        "have": sorted(have),
        "missing": {b: v for b, v in buckets.items()},
        "extra": extra,
        "counts": {"process": len(prof.get("process", set())),
                   "filament": len(prof.get("filament", set())),
                   "machine": len(prof.get("machine", set())),
                   "project": len(proj), "universe": len(universe), "have": len(have)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n清单已存：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
