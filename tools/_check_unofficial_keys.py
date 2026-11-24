"""列出「官方三页查不到」的 defaults 键中，哪些真实工程里存在、哪些会被本程序写入。

用法：
    python tools/_check_unofficial_keys.py --project PATH
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

    in_project = [k for k in unofficial if k in project]
    print(f"defaults 里官方查不到的键：{len(unofficial)}")
    print(f"其中真实工程里存在的：{len(in_project)}")
    for key in in_project:
        spec = schema.PARAMS.get(key)
        kind = spec.kind if spec else "-"
        print(f"  {key:<48} 工程值={project[key]!r:<22} kind={kind}")

    # 规则库其他层（modes / interactions / shape_profiles）里对这些键的操作
    print("\n规则库其他层对这些键的操作：")
    for key in unofficial:
        hits = []
        for mode, node in rules.get("modes", {}).items():
            if key in (node.get("ops") or {}):
                hits.append(f"modes.{mode}={node['ops'][key]}")
        for it in rules.get("interactions", []):
            if key in (it.get("set") or {}) or key in (it.get("ops") or {}):
                hits.append(f"interaction[{it.get('id')}]")
        for proto, node in (rules.get("shape_profiles") or {}).items():
            ops = (node.get("ops") or {}) if isinstance(node, dict) else {}
            if key in ops:
                hits.append(f"shape.{proto}")
        if hits:
            print(f"  {key:<48} {hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
