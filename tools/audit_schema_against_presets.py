"""参数表 vs Bambu Studio 官方预设 全量审计

作用：拿本机 Bambu Studio 官方预设（process / filament / machine）与真实工程，
逐个核对 core.schema 里声明的 366 个参数：
  - 声明类型 vs 实际 JSON 形态（标量 / 数组 / 数组元素是百分比 / 空格分隔向量）
  - 声明区间 vs 官方预设实际取值范围（区间收得太窄会把官方值钳掉）
  - 官方预设里根本没出现过的键（多半是自动计算项，不该由我们写）

输出：shots/schema_audit.json + 控制台摘要
用法：python tools/audit_schema_against_presets.py [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema                                    # noqa: E402

BBL = Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")
PRESET_DIRS = [BBL / "process", BBL / "filament", BBL / "machine"]
USER_PRESET_DIR = Path.home() / "AppData/Roaming/BambuStudio/user"
REAL_PROJECTS = list(Path(r"F:\deep seek").glob("**/*.3mf"))

NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


# ------------------------------------------------------------------ 形态识别

def shape_of(v) -> str:
    """给一个 JSON 值打形态标签。"""
    if isinstance(v, list):
        if not v:
            return "empty_list"
        items = v
    else:
        items = [v]
    kinds = set()
    for it in items:
        if isinstance(it, bool):
            kinds.add("bool")
        elif isinstance(it, (int, float)):
            kinds.add("number")
        elif isinstance(it, str):
            s = it.strip()
            if s.endswith("%"):
                kinds.add("percent")
            elif NUM_RE.match(s):
                kinds.add("numeric_str")
            elif " " in s:
                kinds.add("space_vector")
            elif s.startswith("[") or s.startswith("{"):
                kinds.add("json_str")
            else:
                kinds.add("word")
        else:
            kinds.add(type(it).__name__)
    if len(kinds) == 1:
        k = kinds.pop()
    else:
        k = "mixed(" + "|".join(sorted(kinds)) + ")"
    return f"list[{k}]" if isinstance(v, list) else k


def numeric_values(v):
    """把一个值里能当数字用的部分抠出来（百分比取数值部分，空格向量取每个分量）。

    注意：必须基于「原始 JSON 值」而不是截断后的样本字符串，
    否则 "1500" 被截成 "150" 会造出假越界。
    """
    out = []
    items = v if isinstance(v, list) else [v]
    for it in items:
        if isinstance(it, bool):
            continue
        if isinstance(it, (int, float)):
            out.append(float(it))
            continue
        if not isinstance(it, str):
            continue
        for token in it.replace("%", " ").split():
            if NUM_RE.match(token):
                out.append(float(token))
    return out


def raw_values(samples: Counter) -> list:
    """把样本计数还原成原始值列表（不截断）。"""
    out = []
    for raw, _n in samples.items():
        try:
            out.append(json.loads(raw))
        except (ValueError, TypeError):
            out.append(raw)
    return out


# ------------------------------------------------------------------ 采集

def scan_presets():
    """扫官方预设 + 用户自定义预设，返回 key -> 形态计数 + 取值样本。"""
    shapes: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, Counter] = defaultdict(Counter)
    files = 0
    for d in PRESET_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            files += 1
            for k, v in data.items():
                if k in ("type", "name", "inherits", "from", "setting_id", "instantiation",
                         "description", "compatible_printers", "compatible_machines"):
                    continue
                shapes[k][shape_of(v)] += 1
                samples[k][json.dumps(v, ensure_ascii=False)] += 1
    # 用户自定义预设
    if USER_PRESET_DIR.exists():
        for f in USER_PRESET_DIR.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            files += 1
            for k, v in data.items():
                if k in ("type", "name", "inherits", "from", "setting_id", "instantiation",
                         "description", "compatible_printers", "compatible_machines"):
                    continue
                shapes[k][shape_of(v)] += 1
                samples[k][json.dumps(v, ensure_ascii=False)] += 1
    return files, shapes, samples


def scan_projects():
    """扫真实工程里的 project_settings.config。"""
    shapes: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, Counter] = defaultdict(Counter)
    files = 0
    for p in REAL_PROJECTS:
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                target = None
                for cand in ("Metadata/project_settings.config",
                             "Metadata/project_settings.config.json"):
                    if cand in names:
                        target = cand
                        break
                if not target:
                    continue
                data = json.loads(z.read(target).decode("utf-8"))
        except Exception:
            continue
        files += 1
        for k, v in data.items():
            shapes[k][shape_of(v)] += 1
            samples[k][json.dumps(v, ensure_ascii=False)] += 1
    return files, shapes, samples


# ------------------------------------------------------------------ 核对

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="只输出 JSON 摘要")
    args = ap.parse_args()

    n_preset, p_shapes, p_samples = scan_presets()
    n_proj, j_shapes, j_samples = scan_projects()

    report = {
        "preset_files": n_preset,
        "project_files": n_proj,
        "declared_params": len(schema.PARAMS),
        "preset_key_union": len(p_shapes),
        "project_key_union": len(j_shapes),
        "issues": [],
        "per_key": {},
    }

    for key, s in schema.PARAMS.items():
        psh = p_shapes.get(key)
        jsh = j_shapes.get(key)
        entry = {
            "label": s.label,
            "group": s.group,
            "declared_kind": s.kind,
            "declared_range": [s.vmin, s.vmax],
            "soft": s.soft,
            "preset_shapes": dict(psh) if psh else {},
            "project_shapes": dict(jsh) if jsh else {},
            "preset_samples": p_samples.get(key, Counter()).most_common(3),
        }
        vals = []
        for raw in raw_values(p_samples.get(key, Counter())):
            vals.extend(numeric_values(raw))
        if vals:
            entry["observed_range"] = [min(vals), max(vals)]
        report["per_key"][key] = entry

        issues = []

        # 1) 形态不符：声明标量，官方/工程里却是数组
        if s.kind in (schema.FLOAT, schema.INT, schema.PCT, schema.PCT_NUM):
            observed = list(entry["preset_shapes"]) + list(entry["project_shapes"])
            if any(o.startswith("list[") for o in observed):
                issues.append("形态：声明标量，实际是数组")
        if s.kind == schema.FLOAT:
            observed = list(entry["preset_shapes"]) + list(entry["project_shapes"])
            if any("percent" in o for o in observed):
                issues.append("形态：声明数值，实际是百分比字符串")
            if any("space_vector" in o for o in observed):
                issues.append("形态：声明单值，实际是空格分隔向量")

        # 2) 区间收得太窄，官方取值落在区间外
        if "observed_range" in entry and s.kind not in (schema.ENUM, schema.BOOL,
                                                        schema.ENUM_ARRAY):
            lo, hi = entry["observed_range"]
            if lo < s.vmin - 1e-9 and (hi - lo) > 0:
                issues.append(f"区间：官方最小 {lo:g} < 声明下限 {s.vmin:g}")
            if hi > s.vmax + 1e-9:
                issues.append(f"区间：官方最大 {hi:g} > 声明上限 {s.vmax:g}")

        # 3) 官方预设里根本没这个键
        if not psh:
            issues.append("来源：官方预设未出现（多为自动计算项/用户偏好）")

        if issues:
            report["issues"].append({"key": key, "label": s.label, "issues": issues})

    out = ROOT / "shots" / "schema_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({"issues": len(report["issues"]), "file": str(out)},
                         ensure_ascii=False))
        return 0

    print(f"官方预设文件 {n_preset} 个，工程 {n_proj} 个")
    print(f"声明参数 {len(schema.PARAMS)} 个；预设键并集 {len(p_shapes)}；工程键并集 {len(j_shapes)}")
    print(f"有问题的参数 {len(report['issues'])} 个 → {out}")
    print()
    for it in report["issues"]:
        print(f"[{it['key']}] {it['label']}")
        for msg in it["issues"]:
            print("    -", msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
