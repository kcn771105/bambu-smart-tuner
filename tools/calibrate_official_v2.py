"""把规则库基准层对齐到本机 Bambu Studio 官方预设（v2）。

与 v1（tools/calibrate_from_official.py）的区别：
  1. 参照物改为「0.20mm Standard @BBL <机型>」解析后的完整结果，而不是
     fdm_process_single_common + fdm_process_single_0.20 两个片段。
     官方自己的结构就是这样：机型预设继承通用过程预设，再覆盖速度/加速度。
  2. defaults 层 = X1C 参照预设解析结果（去掉各机型专属差异后的通用部分），
     机型层 = 该机型预设相对 X1C 参照的差异项。
  3. 只搬「切片工艺页（process 归属）」的键；机器页 / 耗材页的键不写进基准层。
  4. schema 标了 preserve 的键（用户实测标定值 / 跟随语义 / 盘面摆位）一律跳过，
     官方值不覆盖用户值。
  5. 耗材基线单独从官方 filament/<name> @base 取，涵盖 PLA / PETG / ASA / ABS / TPU。

用法：
  python tools/calibrate_official_v2.py            # 只报告差异
  python tools/calibrate_official_v2.py --apply    # 写回 rules/BambuRules.json
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

# 各机型的官方 0.20mm Standard 过程预设名
MACHINE_PRESETS = {
    "X1C": "0.20mm Standard @BBL X1C",
    "X1": "0.20mm Standard @BBL X1C",    # X1 / X1E 与 X1C 同机架
    "X1E": "0.20mm Standard @BBL X1C",
    "P1S": "0.20mm Standard @BBL P1P",
    "P1P": "0.20mm Standard @BBL P1P",
    "P2S": "0.20mm Standard @BBL P2S",
    "P2P": "0.20mm Standard @BBL P2S",
    "A1": "0.20mm Standard @BBL A1",
    "A1mini": "0.20mm Standard @BBL A1M",
}
REFERENCE = "0.20mm Standard @BBL X1C"

# 官方耗材预设 → 规则库里的耗材键
FILAMENT_PRESETS = {
    "PLA": "Bambu PLA Basic @base",
    "PETG": "Bambu PETG Basic @base",
    "ASA": "Bambu ASA @base",
    "ABS": "Bambu ABS @base",
    "TPU": "Bambu TPU 95A @base",
}


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
    """只保留切片工艺页的键，并按 schema 还原形态。"""
    out: dict = {}
    for k, v in src.items():
        if k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.PROCESS:
            continue
        spec = schema.spec(k)
        if spec.preserve:          # 用户标定值 / 跟随语义：官方值不采纳
            continue
        tv = typed_value(k, v)
        if tv is not None:
            out[k] = tv
    return out


def filament_view(src: dict) -> dict:
    """耗材页的键（只读参照用）。"""
    out: dict = {}
    for k, v in src.items():
        if k not in schema.PARAMS:
            continue
        if scope.scope_of(k) != scope.FILAMENT:
            continue
        spec = schema.spec(k)
        if spec.preserve:
            continue
        tv = typed_value(k, v)
        if tv is not None:
            out[k] = tv
    return out


# ------------------------------------------------------------------ 构建

def build_layers() -> tuple[dict, dict, dict]:
    """返回 (defaults, 各机型 baseline, 各耗材 baseline)。"""
    ref = process_view(resolve_preset(REFERENCE))

    defaults = dict(ref)

    per_machine: dict = {}
    for mkey, pname in MACHINE_PRESETS.items():
        cur = process_view(resolve_preset(pname))
        node = {k: v for k, v in cur.items() if ref.get(k) != v}
        # 同机架的机型共享一份差异
        per_machine[mkey] = node

    per_filament: dict = {}
    for fkey, pname in FILAMENT_PRESETS.items():
        per_filament[fkey] = filament_view(resolve_preset(pname))

    return defaults, per_machine, per_filament


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写回 rules/BambuRules.json")
    args = ap.parse_args()

    if not BBL.exists():
        print(f"找不到官方预设目录：{BBL}")
        return 1

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    defaults, per_machine, per_filament = build_layers()

    print("=== defaults（通用工艺基线，对齐官方参照预设）===")
    cur = rules["defaults"]
    n_diff = 0
    for k, v in sorted(defaults.items()):
        old = cur.get(k)
        if old is None:
            print(f"  + {k} = {v!r}")
            n_diff += 1
        elif str(old) != str(v) and not (isinstance(old, (int, float))
                                         and isinstance(v, (int, float))
                                         and abs(float(old) - float(v)) < 1e-9):
            print(f"  ~ {k}: {old!r} → {v!r}")
            n_diff += 1
    print(f"defaults 改动 {n_diff} 处 / 官方参照 {len(defaults)} 键")

    for mkey, node in per_machine.items():
        base = rules["printers"].get(mkey, {}).get("baseline", {})
        diffs = [(k, base.get(k), v) for k, v in sorted(node.items())
                 if str(base.get(k)) != str(v)
                 and not (isinstance(base.get(k), (int, float))
                          and isinstance(v, (int, float))
                          and abs(float(base.get(k)) - float(v)) < 1e-9)]
        extra = [k for k in base if k not in node and k not in defaults]
        print(f"=== {mkey} 机型层：差异 {len(diffs)} 处，官方没有但我们有 {len(extra)} 项 {extra}")

    for fkey, node in per_filament.items():
        base = rules["filaments"].get(fkey, {}).get("baseline", {})
        diffs = [(k, base.get(k), v) for k, v in sorted(node.items())
                 if str(base.get(k)) != str(v)
                 and not (isinstance(base.get(k), (int, float))
                          and isinstance(v, (int, float))
                          and abs(float(base.get(k)) - float(v)) < 1e-9)]
        print(f"=== {fkey} 耗材层（只读参照）：差异 {len(diffs)} 处")

    if not args.apply:
        print("\n（加 --apply 才会写回规则库）")
        return 0

    # ---- 写回
    merged = dict(cur)
    merged.update(defaults)
    # defaults 里已被官方覆盖的键，保留官方形态
    rules["defaults"] = merged

    for mkey, node in per_machine.items():
        pnode = rules["printers"].get(mkey)
        if not pnode:
            continue
        base = dict(pnode.get("baseline", {}))
        base.update(node)
        # 官方没有的键不再保留（避免自造值压过官方基线）
        for k in [k for k in base if k not in node and k not in defaults]:
            base.pop(k)
        pnode["baseline"] = base

    for fkey, node in per_filament.items():
        fnode = rules["filaments"].get(fkey)
        if not fnode:
            continue
        base = dict(fnode.get("baseline", {}))
        base.update(node)
        # 耗材层只保留耗材页的键（工艺页的键由 defaults / 机型层负责）
        for k in [k for k in base if scope.scope_of(k) != scope.FILAMENT]:
            base.pop(k)
        fnode["baseline"] = base

    RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写回 {RULES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
