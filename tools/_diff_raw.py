"""原始文本级对比：原工程 vs 优化后工程，逐键列出文本变化。

用法：
    python tools/_diff_raw.py 原文件 优化后文件
"""
from __future__ import annotations

import json
import sys
import zipfile


def load(path: str) -> dict:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("Metadata/project_settings.config").decode("utf-8"))


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    a, b = load(src), load(dst)
    keys = sorted(set(a) | set(b))
    diff = []
    for key in keys:
        if key not in a:
            diff.append((key, "<不存在>", b[key]))
        elif key not in b:
            diff.append((key, a[key], "<被删除>"))
        elif str(a[key]) != str(b[key]):
            diff.append((key, a[key], b[key]))
    print(f"原键数 {len(a)}  新键数 {len(b)}  文本变化 {len(diff)}")
    for key, old, new in diff:
        print(f"  {key:<48} {old!r}  →  {new!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
