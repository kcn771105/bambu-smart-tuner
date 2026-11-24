"""导出官方 process 预设分层，供重建规则库 defaults / printers 基线使用。

用法：
    python tools/_dump_official_layers.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import schema  # noqa: E402

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
PROCESS = os.path.join(BBL, "process")

GENERIC = "fdm_process_single_0.20"
MACHINE_PRESET = {
    "X1C": "0.20mm Standard @BBL X1C",
    "X1": "0.20mm Standard @BBL X1C",
    "X1E": "0.20mm Standard @BBL X1C",
    "P1S": "0.20mm Standard @BBL P1P",
    "P1P": "0.20mm Standard @BBL P1P",
    "P2S": "0.20mm Standard @BBL P2S",
    "P2P": "0.20mm Standard @BBL P2S",
    "A1": "0.20mm Standard @BBL A1",
    "A1mini": "0.20mm Standard @BBL A1M",
    "GENERIC": "0.20mm Standard @BBL X1C",
}


def resolve(stem: str) -> dict:
    chain, seen, cur = [], set(), stem
    while cur and cur not in seen:
        seen.add(cur)
        path = os.path.join(PROCESS, cur + ".json")
        if not os.path.exists(path):
            break
        chain.append(cur)
        with open(path, encoding="utf-8") as fh:
            cur = json.load(fh).get("inherits")
    out: dict = {}
    for name in reversed(chain):
        with open(os.path.join(PROCESS, name + ".json"), encoding="utf-8") as fh:
            for key, value in json.load(fh).items():
                if key not in ("inherits", "name", "description"):
                    out[key] = value
    return out


def main() -> int:
    generic = resolve(GENERIC)
    print(f"通用层 {GENERIC}: {len(generic)} 键")
    known = {k: v for k, v in generic.items() if k in schema.PARAMS}
    print(f"  其中在参数表内：{len(known)}")
    missing = [k for k in generic if k not in schema.PARAMS]
    print(f"  不在参数表内：{len(missing)} -> {missing}")

    with open(os.path.join(ROOT, "rules", "BambuRules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)

    for pkey, pnode in rules["printers"].items():
        preset = MACHINE_PRESET.get(pkey)
        if not preset:
            continue
        full = resolve(preset)
        diff = {}
        for key, value in full.items():
            if key in generic:
                continue
            if key not in schema.PARAMS:
                continue
            diff[key] = value
        cur = pnode.get("baseline", {})
        print(f"\n机型 {pkey}（官方 {preset}）新增 {len(diff)} 键，当前规则库 baseline {len(cur)} 键")
        for key, value in sorted(diff.items()):
            print(f"   {key:<45} 官方={value!r:<26} 现库={cur.get(key, '<无>')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
