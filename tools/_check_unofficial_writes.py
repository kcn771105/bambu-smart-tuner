"""检查「官方查不到」这 116 个键：本程序会不会改它们，改成什么。

用法：
    python tools/_check_unofficial_writes.py --project PATH
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import schema  # noqa: E402

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
PAGES = ("process", "filament", "machine")


def official_keys() -> set[str]:
    keys: set[str] = set()
    for page in PAGES:
        for path in glob.glob(os.path.join(BBL, page, "*.json")):
            try:
                with open(path, encoding="utf-8") as fh:
                    keys.update(json.load(fh).keys())
            except Exception:
                continue
    return keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    args = ap.parse_args()

    with open(os.path.join(ROOT, "rules", "BambuRules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)
    defaults = rules.get("defaults", {})
    off = official_keys()
    unofficial = sorted(k for k in defaults if k not in off)

    with zipfile.ZipFile(args.project) as zf:
        project = json.loads(zf.read("Metadata/project_settings.config").decode("utf-8"))

    # 我们默认值 vs 工程原值（语义比较：把 bool/数组/百分比归一）
    def norm(v):
        if isinstance(v, list):
            v = v[0] if v else ""
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        s = str(v)
        if s.endswith("%"):
            try:
                return f"{float(s[:-1]):g}"
            except ValueError:
                return s
        try:
            return f"{float(s):g}"
        except ValueError:
            return s

    changed = []
    for key in unofficial:
        if key not in project:
            continue
        if norm(defaults[key]) != norm(project[key]):
            changed.append((key, project[key], defaults[key]))

    print(f"官方查不到且工程里存在：{sum(1 for k in unofficial if k in project)}")
    print(f"其中我们默认值 ≠ 工程原值（会被改）：{len(changed)}\n")
    for key, pv, dv in changed:
        spec = schema.PARAMS.get(key)
        kind = spec.kind if spec else "-"
        rng = f"{spec.vmin}~{spec.vmax}" if spec else ""
        print(f"  {key:<48} 工程={pv!r:<20} → 我们默认={dv!r:<20} {kind} {rng}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
