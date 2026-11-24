"""校验规则库各机型 baseline 与官方机型预设的取值差异是否完整。

用法：
    python tools/_check_printer_baseline.py
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
    "X1C": "0.20mm Standard @BBL X1C", "X1": "0.20mm Standard @BBL X1C",
    "X1E": "0.20mm Standard @BBL X1C", "P1S": "0.20mm Standard @BBL P1P",
    "P1P": "0.20mm Standard @BBL P1P", "P2S": "0.20mm Standard @BBL P2S",
    "P2P": "0.20mm Standard @BBL P2S", "A1": "0.20mm Standard @BBL A1",
    "A1mini": "0.20mm Standard @BBL A1M", "GENERIC": "0.20mm Standard @BBL X1C",
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


def flat(value):
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def sem(text: str):
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
    with open(os.path.join(ROOT, "rules", "BambuRules.json"), encoding="utf-8") as fh:
        rules = json.load(fh)
    defaults = rules.get("defaults", {})
    generic = resolve(GENERIC)

    for pkey, preset in MACHINE_PRESET.items():
        full = resolve(preset)
        base = rules["printers"].get(pkey, {}).get("baseline", {})
        missing, mismatch = [], []
        for key, value in full.items():
            if key not in schema.PARAMS:
                continue
            off = sem(flat(value))
            if key in base:
                ours = sem(flat(base[key]))
                if ours != off:
                    mismatch.append((key, value, base[key]))
            elif key in defaults:
                ours = sem(flat(defaults[key]))
                if ours != off:
                    missing.append((key, value, defaults[key]))
            else:
                missing.append((key, value, "<无>"))
        print(f"\n=== {pkey}（官方 {preset}）===")
        print(f"  baseline 覆盖但与官方取值不同：{len(mismatch)}")
        for key, off, our in mismatch:
            print(f"     {key:<42} 官方={off!r:<22} baseline={our!r}")
        print(f"  未被 baseline 覆盖、但与通用层默认不同：{len(missing)}")
        for key, off, our in missing:
            print(f"     {key:<42} 官方={off!r:<22} 默认={our!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
