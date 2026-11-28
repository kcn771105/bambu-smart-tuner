"""逐项核对：工艺页的每一个参数到底能不能改。

三层判定，全部实测，不靠猜：
  ① 能不能解析/格式化  —— schema.PARAMS 里有没有、类型认不认
  ② 改得动改不动      —— 把它扰动成另一个合法值，写盘后重新打开，值是否真的变了
  ③ Studio 认不认     —— 扰动后的值是否会进 different_settings_to_system（否则被预设覆盖）
另附：规则库里有没有任何一层引用它（= 优化时会不会主动调它）。

用法：python tools/audit_writable.py
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import preset_diff, schema, scope_data, threemf  # noqa: E402
from _paths import project as _project, out as _out  # noqa: E402

PROJ = _project()
RULES = ROOT / "rules" / "BambuRules.json"
OUT_MD = ROOT / "shots" / "writable_audit.md"


def perturb(key: str, raw):
    """给一个合法但与现值不同的新值；改不了返回 None。"""
    spec = schema.PARAMS.get(key)
    if spec is None:
        return None
    cur = schema.parse_value(spec, raw)
    if cur is None:
        return None
    kind = spec.kind
    if kind in (schema.FLOAT, schema.INT):
        v = float(cur)
        cands = [v * 1.12, v * 0.85, v + 1, v - 1,
                 spec.vmin + (spec.vmax - spec.vmin) * 0.5]
        for c in cands:
            c = min(max(c, spec.vmin), spec.vmax)
            if kind is schema.INT:
                c = round(c)
            if abs(c - v) > 1e-9:
                return schema.format_value(spec, c, raw)
        return None
    if kind is schema.PCT or kind is schema.PCT_NUM:
        v = float(cur)
        new = min(v + 5, spec.vmax)
        if new == v:
            new = max(v - 5, spec.vmin)
        if new == v:
            return None
        return schema.format_value(spec, new, raw)
    if kind is schema.BOOL:
        return schema.format_value(spec, not bool(cur), raw)
    if kind is schema.ENUM:
        for c in spec.choices or []:
            if str(c).lower() != str(cur).lower():
                return schema.format_value(spec, c, raw)
        return None
    if kind in (schema.ARRAY_FLOAT, schema.ARRAY_PCT):
        try:
            arr = json.loads(raw) if isinstance(raw, str) else list(raw)
            arr = [str(x) for x in arr]
        except Exception:
            return None
        if not arr:
            return None
        try:
            v = float(str(arr[0]).rstrip("%"))
        except ValueError:
            return None
        new = min(v * 1.12 + 1, spec.vmax)
        if abs(new - v) < 1e-9:
            new = max(v * 0.9, spec.vmin)
        if abs(new - v) < 1e-9:
            return None
        arr[0] = f"{new:g}"
        return json.dumps(arr, ensure_ascii=False)
    if kind is schema.ENUM_ARRAY:
        try:
            arr = json.loads(raw) if isinstance(raw, str) else list(raw)
            arr = [str(x) for x in arr]
        except Exception:
            return None
        for c in spec.choices or []:
            if arr and str(arr[0]).lower() != str(c).lower():
                arr[0] = str(c)
                return json.dumps(arr, ensure_ascii=False)
        return None
    return None


def rules_mentions(key: str) -> bool:
    txt = RULES.read_text(encoding="utf-8")
    return f'"{key}"' in txt


def main() -> int:
    if not PROJ.exists():
        print("找不到真实工程：", PROJ)
        return 1
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    proj = threemf.ThreeMfProject.load(PROJ)
    base = copy.deepcopy(proj.settings)

    process_keys = sorted(k for k, v in scope_data.SCOPE.items() if v == "process")
    print(f"工艺页登记 {len(process_keys)} 个键；工程里实际存在 "
          f"{sum(1 for k in process_keys if k in base)} 个")

    # ---------- ① 解析层 ----------
    no_spec = [k for k in process_keys if k not in schema.PARAMS]
    # ---------- ② 写入层：全体扰动一次，写盘后重开比 ----------
    plan: dict[str, tuple[str, object]] = {}
    no_perturb = []
    for k in process_keys:
        if k not in base:
            continue
        spec = schema.PARAMS.get(k)
        # preserve 只是「规则库默认不去覆盖用户的实测值」，
        # 不是「写不进去」：形状层/几何层有明确理由时仍会改它（allow_preserve=True）。
        new = perturb(k, base[k])
        if new is None:
            no_perturb.append(k)
        else:
            plan[k] = (new, base[k])

    proj.settings = copy.deepcopy(base)
    proj.apply({k: v for k, (v, _) in plan.items()})
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "w.3mf"
        proj.save_as(tmp)
        again = threemf.ThreeMfProject.load(tmp)
        back = again.settings

    not_written, equal_preset, not_declared, ok = [], [], [], 0
    preset = preset_diff.load_preset(str(back.get("print_settings_id") or ""), "process") or {}
    decl = preset_diff.process_diff(back, str(back.get("print_settings_id") or ""),
                                    also=list(plan))
    decl_set = set(decl)
    for k, (want, old) in plan.items():
        got = back.get(k)
        same = (str(got).strip() == str(want).strip())
        if not same:
            not_written.append((k, old, want, got))
            continue
        if k in decl_set:
            ok += 1
            continue
        # 没声明但值恰好等于预设值 —— Studio 取预设值正好等于我们要的值，没问题
        pv = preset.get(k)
        if pv is not None and preset_diff._norm(pv) == preset_diff._norm(got):
            equal_preset.append((k, got))
            ok += 1
        else:
            not_declared.append((k, want))

    preserve = [k for k in process_keys
                if k in base and getattr(schema.PARAMS.get(k), "preserve", False)]
    missing = [k for k in process_keys if k not in base]

    # ---------- 报告 ----------
    lines = []
    lines.append("# 工艺页逐项可改性核对\n")
    lines.append(f"- 工艺页登记键：{len(process_keys)}")
    lines.append(f"- 工程里存在：{len(process_keys) - len(missing)}")
    lines.append(f"- **改得动且会声明（Studio 会采用）：{ok}**")
    lines.append(f"- 写盘后值不一致：{len(not_written)}")
    lines.append(f"- 写进去了但没声明：{len(not_declared)}")
    lines.append(f"- 明确 preserve（故意不改）：{len(preserve)}")
    lines.append(f"- 扰动不出新值（枚举只有一项等）：{len(no_perturb)}")
    lines.append(f"- 工程里没有该键：{len(missing)}")
    lines.append(f"- schema 未登记：{len(no_spec)}")

    def block(title, items, fmt=lambda x: f"- `{x}`"):
        if not items:
            return
        lines.append(f"\n## {title}（{len(items)}）\n")
        for it in items:
            lines.append(fmt(it))

    block("写盘后值不一致", not_written,
          lambda t: f"- `{t[0]}`：{t[1]} → 期望 {t[2]}，文件里 {t[3]}")
    block("写进去了但没声明（会被 Studio 预设覆盖）", not_declared,
          lambda t: f"- `{t[0]}` = {t[1]}")
    block("preserve（设计上不写）", preserve)
    block("扰动不出新值", no_perturb)
    block("工程里没有该键", missing)
    if missing:
        # 这些多半不是 Bambu 的键名：查一下官方 227 个 process 预设里出现过几次
        import glob
        import io as _io
        files = glob.glob(str(Path(r"C:\Program Files\Bambu Studio\resources"
                                   r"\profiles\BBL\process") / "*.json"))
        hits = {k: 0 for k in missing}
        for f in files:
            try:
                d = json.load(_io.open(f, encoding="utf-8-sig"))
            except Exception:
                continue
            for k in missing:
                if k in d:
                    hits[k] += 1
        lines.append(f"\n官方 227 个 process 预设里它们的出现次数：\n")
        for k in missing:
            tag = "（Bambu 不用这个键名，写了也不会生效）" if hits[k] == 0 else ""
            lines.append(f"- `{k}`：{hits[k]} 次{tag}")
    block("schema 未登记", no_spec)

    lines.append("\n## 规则库是否会用它们\n")
    unused = [k for k in process_keys if not rules_mentions(k)]
    lines.append(f"- 被规则库任一层引用：{len(process_keys) - len(unused)} / {len(process_keys)}")
    if unused:
        lines.append("- 规则库从不主动调的（仍可手工在 Studio 里改，工具不会碰）：")
        for k in unused:
            lines.append(f"  - `{k}`")

    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    print(f"\n完整报告：{OUT_MD}")

    # 明细也打到控制台，便于即时判断
    for t in not_written:
        print("  ✗ 未写入", t[0], t[1], "→", t[2], "实际", t[3])
    for t in not_declared:
        print("  ✗ 未声明", t[0], "=", t[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
