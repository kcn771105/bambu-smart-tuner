"""语义化比对：我们 defaults 与官方参照预设的真实数值差异。

把「形态差异」（bool vs "0"/"1"、数组 vs 标量、int vs float、"50%" vs 50）归一化后，
只报告真正的数值/枚举取值差异。

用法：
    python tools/_diff_semantic.py [--project PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import schema  # noqa: E402

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
PROCESS = os.path.join(BBL, "process")
REFERENCE = "0.20mm Standard @BBL X1C"


def resolve(stem: str, folder: str) -> dict:
    chain, seen, cur = [], set(), stem
    while cur and cur not in seen:
        seen.add(cur)
        path = os.path.join(folder, cur + ".json")
        if not os.path.exists(path):
            break
        chain.append(cur)
        with open(path, encoding="utf-8") as fh:
            cur = json.load(fh).get("inherits")
    out: dict = {}
    for name in reversed(chain):
        with open(os.path.join(folder, name + ".json"), encoding="utf-8") as fh:
            for key, value in json.load(fh).items():
                if key not in ("inherits", "name", "description"):
                    out[key] = value
    return out


def flat(value):
    """把官方/我们的值归一化到「第一槽的纯文本」。"""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def semantic(text: str):
    """归一化数值语义：'50%'→50.0、'0'/'1'（bool 槽）→数值或 None。"""
    t = text.strip()
    if t.endswith("%"):
        try:
            return float(t[:-1])
        except ValueError:
            return t
    try:
        return float(t)
    except ValueError:
        return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="", help="真实工程路径，用于查该键是否存在")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "rules", "BambuRules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)
    ours = rules.get("defaults", {})
    official = resolve(REFERENCE, PROCESS)

    project: dict = {}
    if args.project:
        with zipfile.ZipFile(args.project) as zf:
            project = json.loads(zf.read("Metadata/project_settings.config").decode("utf-8"))

    print(f"官方参照：{REFERENCE}（解析 {len(official)} 键）\n")
    same, diff = [], []
    for key in sorted(ours):
        if key not in official:
            continue
        a = semantic(flat(official[key]))
        b = semantic(flat(ours[key]))
        if a == b:
            same.append(key)
        else:
            diff.append((key, official[key], ours[key], key in project))

    print(f"语义相同：{len(same)}  语义不同：{len(diff)}\n")
    print("真正不同的键：")
    for key, off, our, in_proj in diff:
        mark = "工程里有" if in_proj else "工程里无"
        print(f"  {key:<45} 官方={off!r:<26} 我们={our!r:<26} {mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
