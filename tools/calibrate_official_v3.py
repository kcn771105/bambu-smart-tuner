"""把规则库对齐到本机 Bambu Studio 官方预设，并清掉非「切片工艺页」的键（v3）。

背景：
  Bambu Studio 的三个页面 == 官方预设的三个目录
      machine/  → 机器页
      filament/ → 耗材页
      process/  → 切片工艺页
  本程序按用户要求只写 process 页，所以规则库的所有「会被写进 3mf 的层」
  （defaults / printers[].baseline / filaments[].baseline / modes[].ops / interactions.set|ops）
  必须只包含 process 归属的键；filament 与 machine 的键只作为「只读上限参照」，
  保留在 filaments[].limits / printers[].limits 里。

参照物：
  process/0.20mm Standard @BBL <机型>.json  （沿 inherits 链解析后的最终值）
  - defaults 层 = X1C 参照预设的 process 键
  - 机型层      = 该机型相对 X1C 参照的差异项
  - 耗材上限    = filament/<name> @base 的 filament_max_volumetric_speed / flow_ratio

用法：
  python tools/calibrate_official_v3.py            # 只报告差异
  python tools/calibrate_official_v3.py --apply    # 写回 rules/BambuRules.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import schema, scope  # noqa: E402

BBL = pathlib.Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")
RULES = ROOT / "rules" / "BambuRules.json"

MACHINE_PRESETS = {
    "X1C": "0.20mm Standard @BBL X1C",
    "X1": "0.20mm Standard @BBL X1C",    # X1 / X1E 与 X1C 同机架
    "X1E": "0.20mm Standard @BBL X1C",
    "P1S": "0.20mm Standard @BBL P1P",   # 官方只有 P1P 预设，P1S 同机架
    "P1P": "0.20mm Standard @BBL P1P",
    "P2S": "0.20mm Standard @BBL P2S",
    "P2P": "0.20mm Standard @BBL P2S",   # 官方只有 P2S 预设，P2P 同平台
    "A1": "0.20mm Standard @BBL A1",
    "A1mini": "0.20mm Standard @BBL A1M",
    "GENERIC": "0.20mm Standard @BBL X1C",   # 兜底用通用层
}
REFERENCE = "0.20mm Standard @BBL X1C"

FILAMENT_PRESETS = {
    "PLA": "Bambu PLA Basic @base",
    "PETG": "Bambu PETG Basic @base",
    "ASA": "Bambu ASA @base",
    "ABS": "Bambu ABS @base",
    "TPU": "Bambu TPU 95A @base",
    "GENERIC": "Bambu PLA Basic @base",
}

#: 官方「按机型」的热端流量上限（Bambu 为每个机型单独标定过）。
#: 找不到机型专属预设时回落到 @base 值。
#: 注意 TPU：@base 写的是 15（通用上限），但官方给 X1C/P2S/A1 等机型
#: 单独标定成 3.6 —— 真实 TPU 只能跑到 3~4 mm³/s，用 @base 会直接把 TPU 打废。
#: PETG 也随机型不同：X1C/P2S 是 13，A1 只有 9，P1 系列没单独标定（按 8 保守）。
FLOW_BY_GROUP = {
    "PLA":    {"X1": 21.0, "P1": 21.0, "P2": 21.0, "A1": 21.0, "GENERIC": 21.0},
    "PETG":   {"X1": 13.0, "P1": 8.0,  "P2": 13.0, "A1": 9.0,  "GENERIC": 8.0},
    "ABS":    {"X1": 16.0, "P1": 16.0, "P2": 16.0, "A1": 16.0, "GENERIC": 16.0},
    "ASA":    {"X1": 18.0, "P1": 18.0, "P2": 18.0, "A1": 18.0, "GENERIC": 18.0},
    "TPU":    {"X1": 3.6,  "P1": 3.6,  "P2": 3.6,  "A1": 3.6,  "GENERIC": 3.6},
    "GENERIC": {"X1": 8.0, "P1": 8.0,  "P2": 8.0,  "A1": 8.0,  "GENERIC": 8.0},
}
#: 耗材层的通用流量上限（无机型专属标定时用这个）
FLOW_BASE = {"PLA": 21.0, "PETG": 8.0, "ABS": 16.0, "ASA": 18.0, "TPU": 3.6,
             "GENERIC": 8.0}


# ------------------------------------------------------------------ 预设读取

def find_preset(name: str) -> pathlib.Path | None:
    for sub in ("process", "filament", "machine"):
        p = BBL / sub / f"{name}.json"
        if p.exists():
            return p
    return None


def resolve_preset(name: str) -> dict:
    """沿 inherits 链合并出最终生效值（链上同名键后者覆盖前者）。"""
    path = find_preset(name)
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    parent = data.get("inherits")
    out = resolve_preset(parent) if parent else {}
    out.update({k: v for k, v in data.items() if k != "inherits"})
    return out


# ------------------------------------------------------------------ 形态还原

def typed_value(key: str, raw):
    """把官方原始值还原成 Bambu 工程里的原生形态。"""
    spec = schema.spec(key)
    if spec is None:
        return None
    kind = spec.kind
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip()

    if kind in (schema.PCT, schema.PCT_NUM, schema.ARRAY_PCT):
        if text.endswith("%"):
            return text
        try:
            return f"{float(text)}%"
        except ValueError:
            return text
    if kind == schema.BOOL:
        if text in ("1", "true", "True"):
            return True
        if text in ("0", "false", "False"):
            return False
        return text
    if kind in (schema.ENUM, schema.ENUM_ARRAY):
        return text
    if kind in (schema.INT, schema.FLOAT, schema.ARRAY_FLOAT):
        try:
            return int(round(float(text))) if kind == schema.INT else float(text)
        except ValueError:
            return text
    return text


def process_view(src: dict) -> dict:
    """切片工艺页的键 + 按 schema 还原形态；preserve 键（用户标定值）不采纳官方值。"""
    out: dict = {}
    for k, v in src.items():
        if k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.PROCESS:
            continue
        if schema.spec(k).preserve:
            continue
        tv = typed_value(k, v)
        if tv is not None:
            out[k] = tv
    return out


# ------------------------------------------------------------------ 构建

def build() -> tuple[dict, dict, dict]:
    ref = process_view(resolve_preset(REFERENCE))

    per_machine: dict = {}
    for mkey, pname in MACHINE_PRESETS.items():
        cur = process_view(resolve_preset(pname))
        per_machine[mkey] = {k: v for k, v in cur.items() if ref.get(k) != v}

    per_filament: dict = {}
    for fkey, pname in FILAMENT_PRESETS.items():
        src = resolve_preset(pname)
        lim: dict = {}
        if "filament_max_volumetric_speed" in src:
            v = schema.numeric(src["filament_max_volumetric_speed"])
            if v:
                lim["max_volumetric_speed"] = float(v)
        if "filament_flow_ratio" in src:
            v = schema.numeric(src["filament_flow_ratio"])
            if v:
                lim["flow_ratio"] = float(v)
        per_filament[fkey] = lim

    return ref, per_machine, per_filament


def filament_limits(fkey: str, group: str) -> tuple[float, float]:
    """取「耗材 × 机型组」的官方热端流量上限与流量比。

    Bambu 为每个机型单独标定过热端流量（同一个 PETG，X1C 是 13、A1 只有 9），
    所以这里按机型组取值；没有专属标定时回落到 @base 的通用值。
    """
    flow = FLOW_BY_GROUP.get(fkey, {}).get(group)
    if flow is None:
        flow = FLOW_BASE.get(fkey, 8.0)
    ratio = {"PLA": 0.98, "PETG": 0.95, "ABS": 0.95, "ASA": 0.95, "TPU": 1.0,
             "GENERIC": 0.95}.get(fkey, 0.95)
    return float(flow), float(ratio)


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    return str(a) == str(b)


# ------------------------------------------------------------------ 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写回 rules/BambuRules.json")
    args = ap.parse_args()

    if not BBL.exists():
        print(f"找不到官方预设目录：{BBL}")
        return 1

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    ref, per_machine, per_filament = build()

    # ---------- 1. defaults：官方参照值覆盖同名键；删掉非工艺页的键
    old_defaults = dict(rules.get("defaults", {}))
    new_defaults = {k: v for k, v in old_defaults.items() if scope.scope_of(k) == scope.PROCESS}
    dropped_defaults = [k for k in old_defaults if k not in new_defaults]
    changed_defaults = []
    for k, v in ref.items():
        if k in new_defaults and not _same(new_defaults[k], v):
            changed_defaults.append((k, new_defaults[k], v))
        new_defaults[k] = v

    print(f"defaults：删掉非工艺页 {len(dropped_defaults)} 键，官方覆盖 {len(changed_defaults)} 处，"
          f"最终 {len(new_defaults)} 键")
    for k, o, n in changed_defaults[:40]:
        print(f"  ~ {k}: {o!r} → {n!r}")

    # ---------- 2. 机型层：重建为「官方差异 + 我们的官方没有的工艺页键」
    for mkey, node in per_machine.items():
        pnode = rules["printers"].get(mkey)
        if not pnode:
            continue
        old = pnode.get("baseline", {})
        keep_extra = {k: v for k, v in old.items()
                      if scope.scope_of(k) == scope.PROCESS and k not in ref}
        new = dict(node)
        new.update(keep_extra)
        pnode["baseline"] = new
        removed = [k for k in old if k not in new]
        changed = [(k, old.get(k), v) for k, v in new.items()
                   if k in old and not _same(old.get(k), v)]
        print(f"printers.{mkey}.baseline：{len(old)} → {len(new)} 键"
              f"（删 {len(removed)}，改 {len(changed)}）")
        if removed:
            print(f"    删: {removed}")

    # ---------- 3. 耗材层：只保留工艺页的键；limits 用官方热端流量上限
    for fkey, lim in per_filament.items():
        fnode = rules["filaments"].get(fkey)
        if not fnode:
            continue
        old = fnode.get("baseline", {})
        new = {k: v for k, v in old.items() if scope.scope_of(k) == scope.PROCESS}
        fnode["baseline"] = new
        lims = dict(fnode.get("limits", {}))
        flow, ratio = filament_limits(fkey, "X1C")
        lims["max_volumetric_speed"] = flow
        lims["flow_ratio"] = ratio
        # 按机型的官方标定值（同一个耗材在不同机型上热端能力不同）
        lims["flow_by_printer"] = {m: filament_limits(fkey, m)[0]
                                   for m in MACHINE_PRESETS}
        fnode["limits"] = lims
        removed = [k for k in old if k not in new]
        print(f"filaments.{fkey}.baseline：{len(old)} → {len(new)} 键（删 {len(removed)}）"
              f"；流量上限 flow={flow} ratio={ratio}")

    # ---------- 4. 模式层：只留工艺页
    for mkey, mnode in rules.get("modes", {}).items():
        ops = mnode.get("ops", {})
        drop = [k for k in ops if scope.scope_of(k) != scope.PROCESS]
        for k in drop:
            ops.pop(k)
        print(f"modes.{mkey}.ops：删掉非工艺页 {len(drop)} 键 → {len(ops)} 键")

    # ---------- 5. 交叉规则：set/ops 只留工艺页，warn 全部保留
    for it in rules.get("interactions", []):
        for field in ("set", "ops"):
            m = it.get(field) or {}
            drop = [k for k in m if scope.scope_of(k) != scope.PROCESS]
            for k in drop:
                m.pop(k)

    rules["defaults"] = new_defaults

    if not args.apply:
        print("\n（加 --apply 才会写回规则库）")
        return 0

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写回 {RULES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
