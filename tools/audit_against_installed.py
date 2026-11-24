"""对着「本机实际装着的 Bambu Studio」审一遍规则库。

做三件事：
1. 读安装目录里的版本号；
2. 把 13 个机型 / 5 种耗材 / 6 个模式 的官方预设沿 inherits 链解开，与 rules/BambuRules.json 逐项比；
3. 列出差异（规则库没写、写错、或不一致）。

用法：python tools/audit_against_installed.py
"""
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STUDIO = Path(r"C:\Program Files\Bambu Studio")
PROFILES = STUDIO / "resources" / "profiles" / "BBL"
RULES = ROOT / "rules" / "BambuRules.json"

# 机型键 -> 官方预设名前缀
MACHINE_NAME = {
    "X1C": "Bambu Lab X1 Carbon", "X1": "Bambu Lab X1", "X1E": "Bambu Lab X1E",
    "P1S": "Bambu Lab P1S", "P1P": "Bambu Lab P1P",
    "P2S": "Bambu Lab P2S", "P2P": "Bambu Lab P2S",
    "A1": "Bambu Lab A1", "A1mini": "Bambu Lab A1 mini",
    "H2D": "Bambu Lab H2D", "H2DP": "Bambu Lab H2D Pro", "H2S": "Bambu Lab H2S",
}
# 耗材键 -> 官方 filament 预设名
FILAMENT_NAME = {
    "PLA": "Bambu PLA Basic @BBL X1C",
    "PETG": "Bambu PETG Basic @BBL X1C",
    "ABS": "Bambu ABS @BBL X1C",
    "ASA": "Bambu ASA @BBL X1C",
    "TPU": "Bambu TPU 95A @BBL X1C",
}
# 模式键 -> 官方 process 预设名
MODE_PROFILE = {
    "balanced": "0.20mm Standard @BBL X1C",
    "strength": "0.20mm Strength @BBL X1C",
    "quality": "0.16mm High Quality @BBL X1C",
    "draft": "0.24mm Draft @BBL X1C",
    "fine": "0.12mm Fine @BBL X1C",
    "ultrafine": "0.08mm Extra Fine @BBL X1C",
}
# 比对哪些工艺项（模式层）
MODE_KEYS = ("layer_height", "outer_wall_speed", "wall_loops",
             "sparse_infill_density", "sparse_infill_pattern",
             "support_threshold_angle", "top_shell_layers")


def studio_version() -> str:
    exe = STUDIO / "bambu-studio.exe"
    if not exe.exists():
        return "(未安装)"
    try:
        import subprocess
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"(Get-Item '{exe}').VersionInfo.FileVersion"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "(读不到)"
    except Exception:
        return "(读不到)"


_CACHE: dict[str, dict] = {}


def resolve(path: Path) -> dict:
    """沿 inherits 链合并（父级先写、子级覆盖）。"""
    key = str(path).lower()
    if key in _CACHE:
        return _CACHE[key]
    data = json.load(io.open(path, encoding="utf-8-sig"))
    parent = data.get("inherits")
    if parent:
        for cand in (path.parent / f"{parent}.json",
                     *PROFILES.glob(f"*/{parent}.json")):
            if cand.exists():
                base = dict(resolve(cand))
                base.update(data)
                _CACHE[key] = base
                return base
    _CACHE[key] = data
    return data


def find(name: str) -> Path | None:
    for sub in ("machine", "process", "filament"):
        p = PROFILES / sub / f"{name}.json"
        if p.exists():
            return p
    return None


def num(v):
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, str):
        v = v.strip().rstrip("%")
        try:
            return float(v)
        except ValueError:
            return None
    return v if isinstance(v, (int, float)) else None


def main() -> int:
    rules = json.load(io.open(RULES, encoding="utf-8-sig"))
    print(f"Bambu Studio 版本：{studio_version()}")
    print(f"预设目录：{PROFILES}")

    # ---------- 1. 机型 limits ----------
    print("\n=== 机型 limits ===")
    bad = 0
    for key, off_name in MACHINE_NAME.items():
        node = rules["printers"].get(key)
        if not node:
            print(f"  {key}: 规则库缺这个机型")
            bad += 1
            continue
        p = find(f"{off_name} 0.4 nozzle") or find(off_name)
        if not p:
            print(f"  {key}: 找不到官方预设 {off_name}")
            bad += 1
            continue
        off = resolve(p)
        lim = node.get("limits", {})
        rows = (
            ("max_speed", "machine_max_speed_x"),
            ("max_accel", "machine_max_acceleration_x"),
            ("max_travel_accel", "machine_max_acceleration_travel"),
            ("max_jerk", "machine_max_jerk_x"),
            ("nozzle_volume", "nozzle_volume"),
            ("min_layer_height", "min_layer_height"),
            ("max_layer_height", "max_layer_height"),
        )
        diffs = []
        for mine, theirs in rows:
            a, b = num(lim.get(mine)), num(off.get(theirs))
            if a is None or b is None:
                continue
            if abs(float(a) - float(b)) > 1e-6:
                diffs.append(f"{mine} {a} vs 官方 {b}")
        if diffs:
            bad += 1
            print(f"  {key}: " + "；".join(diffs))
    if not bad:
        print("  全部一致")

    # ---------- 2. 耗材 0.4 喷嘴流量 ----------
    print("\n=== 耗材流量（0.4 喷嘴，第 0 槽）===")
    bad2 = 0
    for fkey, off_name in FILAMENT_NAME.items():
        p = find(off_name)
        if not p:
            print(f"  {fkey}: 找不到官方预设 {off_name}")
            bad2 += 1
            continue
        off = resolve(p)
        official = num(off.get("filament_max_volumetric_speed"))
        mine = None
        for g, node in rules.get("nozzle_flow", {}).get("by_group", {}).items():
            if fkey in node:
                mine = num(node[fkey].get("0.4"))
                break
        if official is None or mine is None:
            continue
        if abs(official - mine) > 0.01:
            bad2 += 1
            print(f"  {fkey}@{fkey and off_name}: 规则库 {mine} vs 官方 {official}")
    if not bad2:
        print("  全部一致")

    # ---------- 3. 模式档工艺项 ----------
    print("\n=== 模式档（@BBL X1C）===")
    for mkey, off_name in MODE_PROFILE.items():
        ops = rules["modes"].get(mkey, {}).get("ops", {})
        p = find(off_name)
        if not p:
            print(f"  {mkey}: 找不到官方预设 {off_name}")
            continue
        off = resolve(p)
        print(f"  [{mkey}] ← {off_name}")
        for k in MODE_KEYS:
            want = off.get(k)
            op = ops.get(k)
            shown = op if op is not None else "（不动）"
            flag = ""
            if op and isinstance(op, dict) and ("set" in op or "min" in op or "max" in op):
                target = num(op.get("set") or op.get("min") or op.get("max"))
                if target is not None and num(want) is not None:
                    flag = " ✓" if abs(target - num(want)) < 1e-6 else " ✗"
            print(f"      {k:26} 官方 {want!s:14} 规则库 {shown}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
