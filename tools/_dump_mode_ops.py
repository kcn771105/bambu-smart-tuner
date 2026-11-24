"""打印规则库里 modes / interactions 涉及的键与取值（便于人工核对层间语义）。

用法：python tools/_dump_mode_ops.py [key ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parent.parent / "rules" / "BambuRules.json"


def main(argv: list[str]) -> int:
    d = json.loads(RULES.read_text(encoding="utf-8"))
    want = set(argv)
    for mname, mnode in d.get("modes", {}).items():
        ops = mnode.get("ops", {})
        print(f"\n=== mode {mname} ({len(ops)} ops) ===")
        for k, op in ops.items():
            if want and k not in want:
                continue
            print(f"   {k:<38} {json.dumps(op, ensure_ascii=False)}")
    print("\n=== interactions ===")
    for i, node in enumerate(d.get("interactions", [])):
        keys = list((node.get("set") or {}).keys()) + list((node.get("ops") or {}).keys())
        if want and not (want & set(keys)):
            continue
        print(f"[{i}] {node.get('id') or node.get('name')}: when={json.dumps(node.get('when'), ensure_ascii=False)}")
        for k, v in (node.get("set") or {}).items():
            print(f"      set {k:<34} {json.dumps(v, ensure_ascii=False)}")
        for k, v in (node.get("ops") or {}).items():
            print(f"      ops {k:<34} {json.dumps(v, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
