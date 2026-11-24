"""逐键对比：原文件 vs 我们写出的文件，JSON 值类型是否有变化。

Bambu 的 project_settings.config 里几乎所有值都是字符串（数组里也是字符串）。
如果某个键从 "0.2"（str）被写成 0.2（number），Studio 的解析器可能整份拒绝，
表现出来就是「打开了但参数没变」。
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, rules_engine, threemf  # noqa: E402

SRC = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
OUT = Path(r"F:\deep seek\bambu_smart_tuner\dist\_roundtrip.3mf")


def load_raw(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith("project_settings.config")][0]
        return json.loads(z.read(name).decode("utf-8"))


def kind(v) -> str:
    if isinstance(v, list):
        return "list[" + ",".join(sorted({type(x).__name__ for x in v})) + "]"
    return type(v).__name__


def main() -> int:
    a = load_raw(SRC)
    b = load_raw(OUT)

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    print(f"键数 原 {len(a)} / 新 {len(b)}；只在原 {len(only_a)}；只在新 {len(only_b)}")
    if only_a:
        print("  只在原:", only_a[:20])

    diffs = []
    for k in sorted(set(a) & set(b)):
        ka, kb = kind(a[k]), kind(b[k])
        if ka != kb:
            diffs.append((k, ka, a[k], kb, b[k]))
    print(f"\n类型变化 {len(diffs)} 项：")
    for k, ka, va, kb, vb in diffs[:40]:
        print(f"  {k:40} {ka:12} {va!r:24} -> {kb:12} {vb!r}")

    # 元素级：原本全是 str 的数组，我们有没有塞进数字
    elem_bad = []
    for k in sorted(set(a) & set(b)):
        va, vb = a[k], b[k]
        if isinstance(va, list) and isinstance(vb, list):
            ta = {type(x).__name__ for x in va}
            tb = {type(x).__name__ for x in vb}
            if ta != tb:
                elem_bad.append((k, va, vb))
    print(f"\n数组元素类型变化 {len(elem_bad)} 项：")
    for k, va, vb in elem_bad[:40]:
        print(f"  {k:40} {va!r} -> {vb!r}")

    # 值真的变了哪些
    changed = [k for k in sorted(set(a) & set(b)) if a[k] != b[k]]
    print(f"\n实际改动 {len(changed)} 项：")
    for k in changed:
        print(f"  {k:40} {a[k]!r:26} -> {b[k]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
