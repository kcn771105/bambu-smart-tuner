"""把「本软件的优化结果」和「Bambu Studio 官方同档预设」逐项对比。

为什么这是「优化有没有用」的判据
--------------------------------
如果我们的结果和官方同档预设几乎一样，那这个软件只是把官方预设抄了一遍，
用户自己在 Bambu Studio 里选一下就行，没有存在价值。
如果有大量差异，就要能解释每一条差异是「按模型/按耗材/按机型硬件」推出来的，
否则就是乱调。

所以这个工具输出三张表：
    A. 一致：我们和官方同档一样 → 说明基准是对的（不是自造参数）
    B. 差异：我们和官方不同 → 每条都带规则库里的理由链
    C. 官方没有的键：官方预设里根本没这个键（Bambu 新版专有），无法对标

用法：
    python tools/compare_with_official.py [工程路径] [--mode=balanced]
"""
from __future__ import annotations

import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, model_analysis, rules_engine, schema, threemf  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

PROFILE_DIR = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL\process")

MODE_PROFILE = {
    "balanced": "0.20mm Standard",
    "strength": "0.20mm Strength",
    "quality": "0.16mm High Quality",
    "draft": "0.24mm Draft",
    "fine": "0.12mm Fine",
    "ultrafine": "0.08mm Extra Fine",
}

MACHINE_NAME = {
    "X1C": "X1C", "X1": "X1", "X1E": "X1E",
    "P1S": "P1S", "P1P": "P1P", "P2S": "P2S", "P2P": "P2S",
    "A1": "A1", "A1mini": "A1 mini",
    "H2D": "H2D", "H2DP": "H2D Pro", "H2S": "H2S",
}

DEFAULT_PROJECT = _project()


def _load(name: str) -> dict:
    p = PROFILE_DIR / (name + ".json")
    return json.load(io.open(p, encoding="utf-8-sig"))


def resolve(name: str, seen: set | None = None) -> dict:
    """沿 inherits 链合并官方 process 预设（父级先写，子级覆盖）。"""
    seen = seen or set()
    if name in seen:
        return {}
    seen.add(name)
    try:
        raw = _load(name)
    except FileNotFoundError:
        return {}
    parent = raw.pop("inherits", None)
    out = {}
    if parent:
        out.update(resolve(parent, seen))
    out.update(raw)
    return out


def official_for(mode: str, printer_key: str) -> tuple[str, dict]:
    """官方只给部分机型出了全部档位（P2S 只有 Standard / High Quality /
    Balanced Quality，没有 Strength / Draft / Fine / Extra Fine），
    缺失时回退到 X1C 的同档预设 —— 这是官方唯一给出的那套标定。"""
    base = MODE_PROFILE.get(mode, "0.20mm Standard")
    mach = MACHINE_NAME.get(printer_key, printer_key)
    cands = [f"{base} @BBL {mach}", f"{base} @BBL {printer_key}",
             f"{base} @BBL X1C", base]
    for cand in cands:
        try:
            data = resolve(cand)
        except Exception:
            data = {}
        if data:
            return cand, data
    return "", {}


def _n(v):
    """官方预设里速度类键是数组（按喷嘴/耗材分槽），取第 0 槽比较。"""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode_filter = ""
    for a in sys.argv[1:]:
        if a.startswith("--mode="):
            mode_filter = a.split("=", 1)[1]
    project = Path(args[0]) if args else DEFAULT_PROJECT

    proj = threemf.ThreeMfProject.load(project)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)
    profile = model_analysis.analyse(
        proj, overhang_angle=float(proj.settings.get("support_threshold_angle", 45) or 45),
        layer_height=float(proj.settings.get("layer_height", 0.2) or 0.2))

    modes = [mode_filter] if mode_filter else [m[0] for m in eng.mode_choices()]
    print(f"工程 {project.name}｜机型 {det.printer_key}｜耗材 {det.filament_key}")
    for mode in modes:
        pname, off = official_for(mode, det.printer_key)
        res = eng.optimize(proj.settings, printer_key=det.printer_key,
                           filament_key=det.filament_key, nozzle=det.nozzle,
                           mode_key=mode, model_profile=profile, hardware_info=hw)
        same, diff, missing = [], [], []
        for row in res.rows:
            if not (row.changed and row.will_write):
                continue
            key = row.key
            ours = res.values.get(key)
            theirs = off.get(key)
            s = schema.PARAMS.get(key)
            if theirs is None:
                missing.append(key)
                continue
            a, b = _n(ours), _n(theirs)
            if a is not None and b is not None and s and s.kind not in (schema.ENUM, schema.BOOL):
                (same if abs(a - b) <= max(1e-6, abs(b) * 0.02) else diff).append(key)
            else:
                av = ours[0] if isinstance(ours, (list, tuple)) and ours else ours
                bv = theirs[0] if isinstance(theirs, (list, tuple)) and theirs else theirs
                (same if str(av) == str(bv) else diff).append(key)
        print()
        print(f"=== {mode}（官方对标：{pname or '无'}）")
        print(f"    写入 {len(res.write_values)} 项：与官方一致 {len(same)}、"
              f"有差异 {len(diff)}、官方没有该键 {len(missing)}；"
              f"时长 {res.time.delta_pct:+.1f}%")
        if diff:
            print("    —— 差异项（每一条都该有理由）——")
            for key in diff:
                s = schema.PARAMS.get(key)
                label = s.label if s else key
                ours = schema.display(s, _n(res.values.get(key))) if s and _n(res.values.get(key)) is not None else res.values.get(key)
                theirs = schema.display(s, _n(off.get(key))) if s and _n(off.get(key)) is not None else off.get(key)
                why = ""
                for r in res.rows:
                    if r.key == key:
                        why = r.reason
                        break
                print(f"      · {label:<22s} 本软件 {str(ours):>10s} ／ 官方 {str(theirs):>10s}")
                print(f"        理由：{why[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
